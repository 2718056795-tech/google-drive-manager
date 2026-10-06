#!/usr/bin/env python3
"""Persistent Google Drive CLI for Minis sessions."""
import argparse, json, mimetypes, os, sys, time
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("MINIS_GDRIVE_CONFIG_DIR", "/root/.config/minis-google-drive"))
TOKEN_FILE = CONFIG_DIR / "token.json"
FOLDER_MIME = "application/vnd.google-apps.folder"
GOOGLE_EXPORTS = {
    "application/vnd.google-apps.document": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
    "application/vnd.google-apps.spreadsheet": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    "application/vnd.google-apps.presentation": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"),
}


def die(message, code=2):
    print(json.dumps({"ok": False, "error": message}, ensure_ascii=False), file=sys.stderr)
    raise SystemExit(code)


def credentials():
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError as exc:
        die(f"Google API Python 库未安装: {exc}")
    if not TOKEN_FILE.is_file():
        die(f"未找到 OAuth token: {TOKEN_FILE}")
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE))
    if not creds.valid:
        if not creds.refresh_token:
            die("OAuth token 已失效且没有 refresh token，需要重新授权")
        creds.refresh(Request())
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        os.chmod(TOKEN_FILE, 0o600)
    return creds


def execute(request, retries=3):
    last = None
    for attempt in range(retries):
        try:
            return request.execute()
        except Exception as exc:
            last = exc
            if attempt == retries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise last


def service():
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=credentials(), cache_discovery=False)


def esc(value):
    return value.replace("\\", "\\\\").replace("'", "\\'")


def resolve_folder(svc, folder):
    if not folder or folder == "root":
        return "root"
    if folder.startswith("id:"):
        return folder[3:]
    q = f"name = '{esc(folder)}' and mimeType = '{FOLDER_MIME}' and trashed = false"
    rows = execute(svc.files().list(q=q, spaces="drive", fields="files(id,name,modifiedTime)", orderBy="modifiedTime desc", pageSize=100)).get("files", [])
    if not rows:
        die(f"找不到 Google Drive 文件夹: {folder}")
    if len(rows) > 1:
        die(f"同名文件夹不唯一，请改用 id:<folderId>: {folder}")
    return rows[0]["id"]


def ensure_folder(svc, name, parent="root"):
    q = f"name = '{esc(name)}' and mimeType = '{FOLDER_MIME}' and '{parent}' in parents and trashed = false"
    rows = execute(svc.files().list(q=q, spaces="drive", fields="files(id,name)", pageSize=10)).get("files", [])
    if rows:
        return rows[0]["id"], False
    row = execute(svc.files().create(body={"name": name, "mimeType": FOLDER_MIME, "parents": [parent]}, fields="id,name"))
    return row["id"], True


def cmd_status(args):
    svc = service()
    about = execute(svc.about().get(fields="user(emailAddress,displayName),storageQuota(usage,limit)"))
    quota = about.get("storageQuota", {})
    print(json.dumps({"ok": True, "connected": True, "account": about.get("user", {}).get("emailAddress"), "usage_bytes": int(quota.get("usage", 0)), "limit_bytes": int(quota["limit"]) if quota.get("limit") else None, "scope": "full_drive"}, ensure_ascii=False))


def cmd_list(args):
    svc = service(); parent = resolve_folder(svc, args.folder)
    q = f"'{parent}' in parents and trashed = false"
    if args.query:
        q += f" and name contains '{esc(args.query)}'"
    rows = execute(svc.files().list(q=q, spaces="drive", fields="files(id,name,mimeType,size,modifiedTime,webViewLink,parents)", orderBy="folder,name", pageSize=args.limit)).get("files", [])
    print(json.dumps({"ok": True, "folder_id": parent, "count": len(rows), "files": rows}, ensure_ascii=False, indent=2))


def cmd_search(args):
    svc = service(); q = f"name contains '{esc(args.query)}' and trashed = false"
    rows = execute(svc.files().list(q=q, spaces="drive", fields="files(id,name,mimeType,size,modifiedTime,webViewLink,parents)", orderBy="modifiedTime desc", pageSize=args.limit)).get("files", [])
    print(json.dumps({"ok": True, "count": len(rows), "files": rows}, ensure_ascii=False, indent=2))


def cmd_mkdir(args):
    svc = service(); parent = resolve_folder(svc, args.parent)
    folder_id, created = ensure_folder(svc, args.name, parent)
    print(json.dumps({"ok": True, "id": folder_id, "name": args.name, "created": created, "url": f"https://drive.google.com/drive/folders/{folder_id}"}, ensure_ascii=False))


def upload_one(svc, path, parent, overwrite=False):
    from googleapiclient.http import MediaFileUpload
    name = path.name
    q = f"name = '{esc(name)}' and '{parent}' in parents and trashed = false"
    existing = execute(svc.files().list(q=q, spaces="drive", fields="files(id,name)", pageSize=10)).get("files", [])
    media = MediaFileUpload(str(path), mimetype=mimetypes.guess_type(str(path))[0] or "application/octet-stream", resumable=path.stat().st_size > 5 * 1024 * 1024)
    fields = "id,name,size,modifiedTime,webViewLink,parents"
    if existing and overwrite:
        return execute(svc.files().update(fileId=existing[0]["id"], media_body=media, fields=fields)), "updated"
    if existing:
        die(f"目标文件夹已有同名文件，使用 --overwrite 更新: {name}")
    return execute(svc.files().create(body={"name": name, "parents": [parent]}, media_body=media, fields=fields)), "created"


def cmd_upload(args):
    path = Path(args.path).expanduser().resolve()
    if not path.is_file(): die(f"本地文件不存在: {path}")
    svc = service(); parent = resolve_folder(svc, args.folder)
    row, action = upload_one(svc, path, parent, args.overwrite)
    print(json.dumps({"ok": True, "action": action, "file": row}, ensure_ascii=False, indent=2))


def cmd_upload_tree(args):
    root = Path(args.path).expanduser().resolve()
    if not root.is_dir(): die(f"本地目录不存在: {root}")
    svc = service(); parent = resolve_folder(svc, args.folder)
    top_id, _ = ensure_folder(svc, args.name or root.name, parent)
    folder_ids = {Path("."): top_id}; uploaded=[]; skipped=[]
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(part in args.exclude for part in rel.parts):
            skipped.append(str(rel)); continue
        parent_rel = rel.parent
        if parent_rel not in folder_ids:
            current = Path("."); current_id = top_id
            for part in parent_rel.parts:
                current = current / part
                if current not in folder_ids:
                    current_id, _ = ensure_folder(svc, part, current_id); folder_ids[current] = current_id
                else:
                    current_id = folder_ids[current]
        if path.is_dir():
            if rel not in folder_ids:
                folder_ids[rel], _ = ensure_folder(svc, path.name, folder_ids[parent_rel])
        elif path.is_file():
            row, action = upload_one(svc, path, folder_ids[parent_rel], args.overwrite)
            uploaded.append({"path": str(rel), "id": row["id"], "action": action})
    print(json.dumps({"ok": True, "folder_id": top_id, "uploaded_count": len(uploaded), "skipped_count": len(skipped), "uploaded": uploaded, "skipped": skipped}, ensure_ascii=False, indent=2))


def cmd_download(args):
    from googleapiclient.http import MediaIoBaseDownload
    svc = service(); meta = execute(svc.files().get(fileId=args.file_id, fields="id,name,mimeType"))
    out = Path(args.output).expanduser() if args.output else Path(meta["name"])
    mime = meta["mimeType"]
    if mime in GOOGLE_EXPORTS:
        export_mime, suffix = GOOGLE_EXPORTS[mime]
        if out.suffix == "": out = out.with_suffix(suffix)
        request = svc.files().export_media(fileId=args.file_id, mimeType=export_mime)
    elif mime.startswith("application/vnd.google-apps."):
        die(f"暂不支持导出该 Google 原生类型: {mime}")
    else:
        request = svc.files().get_media(fileId=args.file_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as fh:
        dl = MediaIoBaseDownload(fh, request)
        done=False
        while not done:
            _, done = dl.next_chunk()
    print(json.dumps({"ok": True, "path": str(out.resolve()), "name": meta["name"], "mimeType": mime}, ensure_ascii=False))


def cmd_delete(args):
    if not args.yes: die("删除需显式传入 --yes")
    execute(service().files().delete(fileId=args.file_id))
    print(json.dumps({"ok": True, "deleted": args.file_id}, ensure_ascii=False))


def parser():
    p=argparse.ArgumentParser(description="Minis Google Drive persistent CLI")
    sp=p.add_subparsers(dest="command", required=True)
    x=sp.add_parser("status"); x.set_defaults(func=cmd_status)
    x=sp.add_parser("list"); x.add_argument("--folder",default="root"); x.add_argument("--query"); x.add_argument("--limit",type=int,default=100); x.set_defaults(func=cmd_list)
    x=sp.add_parser("search"); x.add_argument("query"); x.add_argument("--limit",type=int,default=100); x.set_defaults(func=cmd_search)
    x=sp.add_parser("mkdir"); x.add_argument("name"); x.add_argument("--parent",default="root"); x.set_defaults(func=cmd_mkdir)
    x=sp.add_parser("upload"); x.add_argument("path"); x.add_argument("--folder",default="root"); x.add_argument("--overwrite",action="store_true"); x.set_defaults(func=cmd_upload)
    x=sp.add_parser("upload-tree"); x.add_argument("path"); x.add_argument("--folder",default="root"); x.add_argument("--name"); x.add_argument("--overwrite",action="store_true"); x.add_argument("--exclude",action="append",default=[".git","__pycache__","node_modules","auth_cookies.txt","credentials.json","token.json","google_drive_service.json"]); x.set_defaults(func=cmd_upload_tree)
    x=sp.add_parser("download"); x.add_argument("file_id"); x.add_argument("--output"); x.set_defaults(func=cmd_download)
    x=sp.add_parser("delete"); x.add_argument("file_id"); x.add_argument("--yes",action="store_true"); x.set_defaults(func=cmd_delete)
    return p


if __name__ == "__main__":
    a=parser().parse_args(); a.func(a)
