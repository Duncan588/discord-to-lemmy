#!/usr/bin/env python3
"""Import Discord-Analytics-Dashboard SQLite data (threads/messages/users/reactions)
into a Lemmy 0.19 Postgres database as one community. Idempotent per thread."""
import argparse, os, sqlite3, time, psycopg2
from psycopg2.extras import execute_values

E = os.environ.get
ap = argparse.ArgumentParser()
ap.add_argument("--source", default=E("SOURCE_DB", "data/discord_data.db"))
ap.add_argument("--portal", default=E("PORTAL_DB", "data/portal.db"), help="optional DB with global_blacklist(user_id)")
ap.add_argument("--guild", default=E("GUILD_ID") or None)
ap.add_argument("--category", default=E("CATEGORY_ID") or None)
ap.add_argument("--limit", type=int, default=int(E("THREAD_LIMIT", "500")), help="threads to import, 0 = all")
ap.add_argument("--order", choices=["recent", "oldest"], default="recent")
ap.add_argument("--community", default=E("COMMUNITY_NAME", "discord"))
ap.add_argument("--title", default=E("COMMUNITY_TITLE", "Discord archive"))
ap.add_argument("--blacklist", default=E("BLACKLIST_IDS", ""), help="comma-separated Discord user IDs to skip")
ap.add_argument("--host", default=E("LEMMY_HOST", "localhost:8536"))
ap.add_argument("--no-reactions", action="store_true")
a = ap.parse_args()
BASE = "http://" + a.host

src = sqlite3.connect(f"file:{a.source}?mode=ro", uri=True)
bl = {x.strip() for x in a.blacklist.split(",") if x.strip()}
if a.portal and os.path.exists(a.portal):
    try: bl |= {r[0] for r in sqlite3.connect(f"file:{a.portal}?mode=ro", uri=True).execute("select user_id from global_blacklist")}
    except sqlite3.Error as e: print("note: no global_blacklist in portal db:", e)
print(f"blacklisted users: {len(bl)}")

pg = psycopg2.connect(host=E("PG_HOST", "postgres"), user=E("PG_USER", "lemmy"), password=E("PG_PW"), dbname=E("PG_DB", "lemmy"))
cur = pg.cursor()
cur.execute("select id from instance where domain=%s", (a.host,)); r = cur.fetchone()
if not r: cur.execute("select instance_id from site order by id limit 1"); r = cur.fetchone()
inst = r[0]
t0 = time.time()

cur.execute("select id from community where name=%s", (a.community,)); r = cur.fetchone()
if r: comm = r[0]
else:
    u = f"{BASE}/c/{a.community}"
    cur.execute("""insert into community(name,title,description,actor_id,local,public_key,inbox_url,followers_url,instance_id,published)
       values(%s,%s,'Imported from Discord',%s,true,'none',%s,%s,%s,now()) returning id""",
       (a.community, a.title[:255], u, u + "/inbox", u + "/followers", inst)); comm = cur.fetchone()[0]

where, args = [], []
if a.guild: where.append("guild_id=?"); args.append(a.guild)
if a.category: where.append("category_id=?"); args.append(a.category)
q = "select thread_id,name from threads" + (" where " + " and ".join(where) if where else "")
q += " order by last_active_at " + ("desc" if a.order == "recent" else "asc")
if a.limit: q += f" limit {a.limit}"
threads = src.execute(q, args).fetchall()

users = {r[0]: r[1:] for r in src.execute("select user_id,username,nickname,is_bot from users")}
cur.execute("select name,id from person where name like 'd%%' and local")
pmap = {n[1:]: i for n, i in cur.fetchall() if n[1:].isdigit()}

def person(uid):
    """One local Lemmy person per Discord author (name d<discord_id>); unusable password."""
    if uid in pmap: return pmap[uid]
    un, nick, bot = users.get(uid, (None, None, 0))
    deleted = un is None or un.startswith("deleted_user")
    disp = ("Deleted User" if deleted else (nick or un or uid))[:255]
    name = "d" + uid; u = f"{BASE}/u/{name}"
    cur.execute("""insert into person(name,display_name,actor_id,local,public_key,inbox_url,instance_id,bot_account,published)
       values(%s,%s,%s,true,'none',%s,%s,%s,'2015-05-13') returning id""", (name, disp, u, u + "/inbox", inst, bool(bot)))
    pid = cur.fetchone()[0]
    cur.execute("insert into local_user(person_id,password_encrypted,accepted_application,email_verified) values(%s,'!',true,true)", (pid,))
    pmap[uid] = pid; return pid

cur.execute("select ap_id from post where community_id=%s", (comm,))
done = {x.rsplit("-", 1)[-1] for (x,) in cur.fetchall()}
np = nc = skipped = 0
CPFX = f"{BASE}/comment/disc-"
for tid, tname in threads:
    if tid in done: continue
    msgs = src.execute("select message_id,author_id,coalesce(content,''),timestamp,reply_to_msg_id from messages "
                       "where thread_id=? order by timestamp,message_id", (tid,)).fetchall()
    rc = {} if a.no_reactions else dict(src.execute(
        "select message_id,count(*) from reactions where message_id in (select message_id from messages where thread_id=?) group by 1", (tid,)).fetchall())
    keep = [m for m in msgs if m[1] not in bl]; skipped += len(msgs) - len(keep)
    if not keep: continue
    first = keep[0]
    cur.execute("""insert into post(name,body,creator_id,community_id,published,ap_id,local,language_id)
       values(%s,%s,%s,%s,%s,%s,true,0) returning id""",
       ((tname or "(untitled)")[:200], first[2] or "(attachment)", person(first[1]), comm, first[3], f"{BASE}/post/disc-{tid}"))
    post = cur.fetchone()[0]; np += 1
    if rc.get(first[0]): cur.execute("update post_aggregates set score=%s,upvotes=%s where post_id=%s", (rc[first[0]], rc[first[0]], post))
    paths, rows = {}, []
    for mid, au, ct, ts, rep in keep[1:]:
        cur.execute("select nextval(pg_get_serial_sequence('comment','id'))"); cid = cur.fetchone()[0]
        path = (paths.get(rep) or "0") + "." + str(cid); paths[mid] = path   # reply tree via reply_to_msg_id
        rows.append((cid, person(au), post, ct or "(attachment)", ts, CPFX + mid, True, path, 0))
    if rows:
        execute_values(cur, "insert into comment(id,creator_id,post_id,content,published,ap_id,local,path,language_id) values %s",
                       rows, template="(%s,%s,%s,%s,%s,%s,%s,%s::ltree,%s)", page_size=1000)
        nc += len(rows)
        sc = [(rc[m[0]], CPFX + m[0]) for m in keep[1:] if rc.get(m[0])]
        if sc: execute_values(cur, "update comment_aggregates ca set score=v.s,upvotes=v.s from (values %s) v(s,ap) "
                              "join comment c on c.ap_id=v.ap where ca.comment_id=c.id", sc)
    pg.commit()

# recompute aggregates
cur.execute("""update comment_aggregates ca set child_count=x.n from (select c.id,(select count(*) from comment c2 where c2.path <@ c.path)-1 n
   from comment c join post p on p.id=c.post_id where p.community_id=%s) x where ca.comment_id=x.id""", (comm,))
cur.execute("""update post_aggregates pa set comments=x.n,newest_comment_time=x.mx,newest_comment_time_necro=x.mx
   from (select post_id,count(*) n,max(published) mx from comment group by 1) x where pa.post_id=x.post_id and pa.community_id=%s""", (comm,))
cur.execute("""update community_aggregates set posts=(select count(*) from post where community_id=%s),
   comments=(select count(*) from comment c join post p on p.id=c.post_id where p.community_id=%s) where community_id=%s""", (comm, comm, comm))
cur.execute("update site_aggregates set users=(select count(*) from local_user),posts=(select count(*) from post),comments=(select count(*) from comment)")
pg.commit()

cur.execute("select count(*) from post where community_id=%s", (comm,)); lp = cur.fetchone()[0]
cur.execute("select count(*) from comment c join post p on p.id=c.post_id where p.community_id=%s", (comm,)); lc = cur.fetchone()[0]
print(f"imported: posts={np} comments={nc} skipped_blacklisted_msgs={skipped} persons={len(pmap)} in {time.time()-t0:.0f}s")
print(f"community '{a.community}' now has posts={lp} comments={lc} (source threads selected={len(threads)})")
