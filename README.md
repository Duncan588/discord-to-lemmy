# discord-to-lemmy

把 Discord-Analytics-Dashboard 导出的 SQLite 数据库（`discord_data.db`）转成 Lemmy 0.19 论坛：每个 Discord 帖子 → Lemmy 帖子，帖子里的消息 → 楼中楼评论，Discord 作者 → Lemmy 本地用户，保留原始作者和时间。

> **English summary:** Converts a Discord-Analytics-Dashboard SQLite DB into a private Lemmy 0.19 instance. Discord forum threads become posts, the first message becomes the post body, later messages become comments threaded via `reply_to_msg_id`, reaction counts become vote scores, each author becomes a local Lemmy user, and original timestamps are kept. Inserts go directly into Postgres. Runs are idempotent per thread. An optional restic (e.g. Cloudflare R2) restore script is included. MIT licensed.

## 功能
- 帖子 → `post`：标题是帖子名，正文是第一条消息，时间是原始发帖时间
- 后续消息 → `comment`：按 `reply_to_msg_id` 生成 ltree 路径，回复关系变成楼中楼
- 每个 Discord 作者 → 一个本地用户（用户名 `d<discord_id>`，显示名用昵称或用户名）；已销号的用户显示为 `Deleted User`
- 表情回应 → 只换成点赞数（`score/upvotes`），表情种类会丢
- 可以排除黑名单用户：用 `BLACKLIST_IDS` 指定，或者读 portal.db 里的 `global_blacklist` 表
- 导入完会重算帖子、评论、社区和站点的统计数；按帖子去重，可以重复运行
- 实例默认设为必须登录才能看，关闭跨站互通，关闭注册

## 环境要求
- Linux，装好 Docker 和 Docker Compose v2，再装 `envsubst`（Ubuntu 上是 `gettext-base` 包）
- 建议 4 核、8G 内存；硬盘至少留出源库大小的 3 倍
- 源库的表结构：`threads(thread_id,category_id,name,guild_id,last_active_at)`、`messages(message_id,thread_id,author_id,content,timestamp,reply_to_msg_id)`、`users(user_id,username,nickname,is_bot)`、`reactions(message_id,...)`

## 使用步骤
```bash
git clone https://github.com/Duncan588/discord-to-lemmy && cd discord-to-lemmy
cp .env.example .env && chmod 600 .env   # 填好 LEMMY_HOST、各项密码、导入选项
```
1. **准备源库**：把 `discord_data.db` 放到 `data/`。如果要从 restic 备份（比如 Cloudflare R2）恢复，在 `.env` 里填好 `RESTIC_*` 和 `AWS_*`，然后运行 `./restore.sh`。
2. **启动 Lemmy**：`./setup.sh`。它会生成 `lemmy.hjson`、修好 pict-rs 文件夹的权限、启动服务，并设成必须登录、关闭跨站和注册。
3. **导入**：
   ```bash
   ./run_import.sh                                   # 用 .env 里的默认值
   ./run_import.sh --category 123 --limit 1000       # 指定分类，导入 1000 个帖子
   ./run_import.sh --limit 0 --order oldest           # 全量导入，从最早的开始
   ./run_import.sh --blacklist 111,222 --no-reactions
   ```
4. **验证**：运行 `./verify.sh`，会用管理员登录并打出社区的帖子数和评论数，再列出最早的几个帖子，可以跟源库核对。
5. 浏览器打开 `http://<LEMMY_HOST>`。

## 限制
- **Lemmy 0.19 不支持 Discord 登录**：OAuth 要 1.0（目前还是测试版）才有，而且回调地址必须能从外网访问，比如要先接 Cloudflare Tunnel。
- **导入的用户不能登录**：密码是故意设成无效的，以后要靠 OAuth 认领或管理员重置。
- **pict-rs 文件夹权限**：`volumes/pictrs` 的所有者必须是 `991:991`，否则 pict-rs 起不来。`setup.sh` 会尝试用 sudo 改。
- 附件和图片不导入，只放一个占位文字；Discord 上改过或删掉的消息不会同步。
- 上万条消息的大帖在 Lemmy 网页上会比较卡。
- 脚本直接写 Lemmy 的数据库，只在 0.19.20 上测过；升级 Lemmy 前要重新验证。

## License
MIT
