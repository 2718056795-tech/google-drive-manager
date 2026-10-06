#!/usr/bin/env python3
import json, mimetypes, os, sys, urllib.parse, urllib.request
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
TOKEN='/root/.config/minis-google-drive/token.json'
FOLDER='application/vnd.google-apps.folder'

def creds():
 c=Credentials.from_authorized_user_file(TOKEN)
 if not c.valid:
  c.refresh(Request()); open(TOKEN,'w').write(c.to_json()); os.chmod(TOKEN,0o600)
 return c

def api(c,path,method='GET',body=None,ctype='application/json'):
 d=None if body is None else (json.dumps(body).encode() if ctype=='application/json' else body)
 r=urllib.request.Request('https://www.googleapis.com'+path,data=d,method=method,headers={'Authorization':'Bearer '+c.token,'Content-Type':ctype})
 return json.load(urllib.request.urlopen(r))

def find(c,name,parent=None,folder=None):
 q=[f"name='{name.replace(chr(39), chr(92)+chr(39))}'","trashed=false"]
 if parent:q.append(f"'{parent}' in parents")
 if folder is True:q.append(f"mimeType='{FOLDER}'")
 u='/drive/v3/files?q='+urllib.parse.quote(' and '.join(q))+'&fields=files(id,name,mimeType,md5Checksum)'
 return api(c,u).get('files',[])

def mkdir(c,name,parent):
 x=find(c,name,parent,True)
 return x[0]['id'] if x else api(c,'/drive/v3/files','POST',{'name':name,'mimeType':FOLDER,'parents':[parent]})['id']

def upload(c,path,parent):
 name=os.path.basename(path); old=find(c,name,parent); meta={'name':name}
 raw=open(path,'rb').read(); boundary='minis_upload_boundary'
 pre=(f'--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'+json.dumps(meta)+'\r\n'+f'--{boundary}\r\nContent-Type: text/markdown\r\n\r\n').encode(); post=(f'\r\n--{boundary}--').encode(); body=pre+raw+post
 if old: endpoint=f'/upload/drive/v3/files/{old[0]["id"]}?uploadType=multipart&fields=id,name,md5Checksum'; method='PATCH'
 else: meta={'name':name,'parents':[parent]}; pre=(f'--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'+json.dumps(meta)+'\r\n'+f'--{boundary}\r\nContent-Type: text/markdown\r\n\r\n').encode(); body=pre+raw+post; endpoint='/upload/drive/v3/files?uploadType=multipart&fields=id,name,md5Checksum'; method='POST'
 return api(c,endpoint,method,body,f'multipart/related; boundary={boundary}')

if __name__=='__main__':
 c=creds(); root=find(c,'9_openminis_skills',None,True)[0]['id']; sub=mkdir(c,sys.argv[1],root); print(json.dumps(upload(c,sys.argv[2],sub),ensure_ascii=False))
