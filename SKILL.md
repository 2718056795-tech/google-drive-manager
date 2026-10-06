---
name: google-drive-manager
version: 3.0.0
description: 管理用户已授权的 Google Drive：上传本地文件或目录、下载、列出、搜索、创建文件夹、备份与同步。用户说“上传到 Drive / 谷歌云盘”“同步到 Google Drive”“从 Drive 下载”“查云盘文件”“把技能同步到 iCloud 和 Drive”时必须使用本技能；新对话也应直接调用持久化 CLI，不要改走浏览器登录，也不要要求重新授权，除非 CLI 明确报告 token 失效。
---

# Google Drive Manager

## 固定环境

- 已授权账户：`xszbelief2@gmail.com`
- 持久化 CLI：`/var/minis/skills/google-drive-manager/scripts/gdrive.py`
- OAuth 凭据保存在私有目录 `/root/.config/minis-google-drive/`；**不要读取、打印、上传、复制到共享目录或聊天**。
- 所有命令可从任意工作目录运行，新对话无需依赖 `workspace` 当前目录。

## 必须遵循

1. 用户要求上传、下载、搜索或同步时，直接运行 CLI；不要先检查浏览器 Cookie 或 Google 网页登录。
2. 仅当命令报告 OAuth 无效且无法刷新时，才要求重新授权。
3. Google Drive 只作为**技能库二次备份**：`9_openminis_skills/` 必须与本地 `/var/minis/skills/`、iCloud `9_openminis_skills/` 一样，以普通文件夹/文件直接展开；禁止压缩包、manifest 或 `incremental-files` 中间层。普通临时文件不得上传，除非用户当次明确指定。
4. 用户明确要求上传单个业务文件时，才按其指定目录上传；默认不覆盖同名文件，明确要求更新时使用 `--overwrite`。
5. 一般删除 Drive 内容属于破坏性操作，执行前向用户确认；但技能镜像使用 `rclone sync`，删除本地技能文件会同步移入 Drive 回收站，这是用户明确要求的镜像语义。
6. **绝不上传秘密**：`credentials.json`、`token.json`、`google_drive_service.json`、登录 Cookie、API key、密码、SSH 私钥及类似凭据。
7. 技能二次备份固定运行 `scripts/backup_skills.py`：脚本以 `rclone sync --checksum` 将本地技能库直接镜像到 Drive 根目录，未变化文件只校验不上传，新增/修改文件按原路径上传，删除项同步移入回收站；完成后必须逐文件校验。
8. 禁止为技能备份创建或保留整库压缩包、manifest、`incremental-files`、日期快照及其他包装层；Drive 中应能直接浏览每个技能目录。
9. Google Drive 是新增备份目标，现有 iCloud 镜像机制保持不变，除非用户明确要求改变。
10. 技能文件发生新建、编辑或删除时：本地 `/var/minis/skills/` 是唯一真源；先同步 iCloud 镜像并校验，再运行 Drive 展开镜像。不得把凭据随技能上传。

## 常用命令

```bash
CLI=/var/minis/skills/google-drive-manager/scripts/gdrive.py

# 实时验证连接
python3 "$CLI" status

# 列根目录或指定文件夹
python3 "$CLI" list
python3 "$CLI" list --folder "文件夹名"
python3 "$CLI" list --folder id:FOLDER_ID

# 全盘按名称搜索
python3 "$CLI" search "关键词"

# 创建文件夹
python3 "$CLI" mkdir "目标文件夹"
python3 "$CLI" mkdir "子文件夹" --parent id:FOLDER_ID

# 上传单个文件
python3 "$CLI" upload "/absolute/path/file.ext" --folder "目标文件夹"
python3 "$CLI" upload "/absolute/path/file.ext" --folder id:FOLDER_ID --overwrite

# 上传完整目录并保留目录结构（自动排除秘密和依赖缓存）
python3 "$CLI" upload-tree "/absolute/path/folder" --folder "目标父文件夹"

# 下载普通文件；Google Docs/Sheets/Slides 自动导出为 docx/xlsx/pptx
python3 "$CLI" download FILE_ID --output "/var/minis/workspace/name.ext"

# 删除（先获得用户确认）
python3 "$CLI" delete FILE_ID --yes
```

## 技能双云同步流程

用户要求更新技能并同步 iCloud 与 Drive 时：

1. 修改本地技能并完成测试。
2. 同步本地技能目录到 iCloud `9_openminis_skills/<skill>/`，校验文件数和哈希。
3. 执行展开目录镜像：
   ```bash
   python3 /var/minis/skills/google-drive-manager/scripts/backup_skills.py
   ```
4. `rclone sync --checksum` 只上传新增/内容变化的文件；未变化文件不重传。脚本自动排除 `.git`、`__pycache__`、`node_modules`、Cookie、OAuth 与密钥文件。
5. 脚本随后运行逐文件 checksum 校验；只有输出 `file_count` 与本地一致且全部状态为 `=`，才能宣称成功。
6. Drive `9_openminis_skills/` 顶层只应出现本地技能库的目录/文件，结构与 iCloud 镜像一致；不应出现压缩归档或中间层。

## 故障判断

- `status` 成功：连接可用，可直接操作。
- 找不到同名文件夹：先 `mkdir`，再上传。
- 同名文件夹不唯一：用 `search` 找 ID，再传 `id:FOLDER_ID`。
- 401/invalid_grant 且自动刷新失败：才重新授权。
- 网络瞬时错误：重试 1–3 次并退避；不要误判为账户未连接。
