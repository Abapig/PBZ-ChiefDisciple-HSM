"""Export this project's user-facing transcript and a portable documentation bundle.

Reads only the named session; does not publish, modify UE assets, or include reasoning.
Uses Python standard library, including a small OOXML writer for the Word copy.
"""
from pathlib import Path
import base64,collections,datetime,hashlib,html,json,re,shutil,struct,tomllib,zipfile
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'Documentation/影之刃零复刻项目档案_2026-11-13'
SESSION=Path('C:/Users/Lenovo/.codex/sessions/2026/11/11/rollout-2026-11-11T15-43-24-01a1c98f-c2e0-7e42-a0d0-3e68bc871e53.jsonl')
CUTOFF='把这个影之刃零复刻项目及其前置的MCP配置过程整理成一份文档放在文件夹中，要求：'
TITLE='影之刃零复刻项目完整记录与通用流程'
TZ=datetime.timezone(datetime.timedelta(hours=8))

def sha(b):return hashlib.sha256(b).hexdigest()
def write(path,text):
    path=OUT/path;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf8');return path
def dump(path,obj):return write(path,json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def text_content(p):return '\n'.join(b.get('text','') for b in p.get('content',[]) if b.get('type') in ('input_text','output_text','text','Text'))
def local_time(s):return datetime.datetime.fromisoformat(s.replace('Z','+00:00')).astimezone(TZ).strftime('%Y-%m-%d %H:%M:%S')

def extract():
    raw=SESSION.read_bytes();records=[];cutoff=None
    for ln,line in enumerate(raw.splitlines(),1):
        try:r=json.loads(line)
        except json.JSONDecodeError:continue
        records.append((ln,r));p=r.get('payload',{})
        if r.get('type')=='response_item' and p.get('role')=='user' and CUTOFF in text_content(p):cutoff=ln
    assert cutoff,'Archive request not found in named session'
    records=[(ln,r) for ln,r in records if ln<=cutoff]
    summaries=[r['payload'].get('message','') for _,r in records if r.get('type')=='compacted']
    messages=[];excluded=collections.Counter();attachments=[];response_ids=set()
    for ln,r in records:
        p=r.get('payload',{});typ=r.get('type')
        if typ=='response_item' and p.get('type')=='message' and p.get('role') in ('user','assistant'):
            role=p['role'];body=text_content(p)
            if body.startswith('<environment_context>'):
                excluded['environment_messages']+=1;continue
            if role=='assistant' and len(body)>4000 and any(s.endswith(body) or s.endswith(body+'\n') for s in summaries):
                excluded['compaction_summaries']+=1;continue
            if p.get('channel') in ('analysis','summary'):
                excluded['internal_channels']+=1;continue
            msg={'source_line':ln,'source_type':'response_item/message','id':p.get('id'),
                 'timestamp_utc':r.get('timestamp'),'role':role,'phase':p.get('phase'),'text':body,
                 'text_sha256':sha(body.encode('utf8')),'attachments':[]}
            msg['timestamp_beijing']=local_time(msg['timestamp_utc'])
            for b in p.get('content',[]):
                if b.get('type')=='input_image':
                    url=b.get('image_url','');url=url.get('url','') if isinstance(url,dict) else url
                    if url.startswith('data:image/'):
                        header,data=url.split(',',1);ext='png' if 'png' in header else 'jpg'
                        image_bytes=base64.b64decode(data)
                        rel='图片/用户原始参考图_'+str(len(attachments)+1)+'.'+ext
                        f=OUT/rel;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(image_bytes)
                        item={'path':rel,'sha256':sha(image_bytes),'source':'session input_image','source_line':ln,'bytes':len(image_bytes)}
                        attachments.append(item);msg['attachments'].append(item)
            messages.append(msg);response_ids.add(p.get('id'))
        elif typ=='response_item' and p.get('type')=='function_call' and p.get('name')=='request_user_input_async':
            args=json.loads(p.get('arguments','{}'))
            # These are visible questions, not internal tool execution details.
            body='\n\n'.join(q['title']+('\n选项：'+'；'.join(q['options']) if q.get('options') else '') for q in args.get('questions',[]))
            messages.append({'source_line':ln,'source_type':'user_visible_question','id':p.get('id'),
                             'timestamp_utc':r['timestamp'],'timestamp_beijing':local_time(r['timestamp']),
                             'role':'assistant_question','phase':'question','text':body,'original_question_arguments':args,
                             'text_sha256':sha(body.encode()),'attachments':[]})
    # Reconcile display-event mirrors to avoid accidentally omitting a visible message.
    fallbacks=0
    for ln,r in records:
        p=r.get('payload',{});item=p.get('item',{})
        if r.get('type')!='event_msg' or p.get('type')!='item_completed' or item.get('type') not in ('AgentMessage','UserMessage'):continue
        role='assistant' if item['type']=='AgentMessage' else 'user';body=text_content(item)
        if len(body)>4000 and any(s.endswith(body) or s.endswith(body+'\n') for s in summaries):continue
        if item.get('id') in response_ids:continue
        # User display IDs and stored message IDs may differ. Only deduplicate mirror pairs.
        def mirror_text(s):return re.sub(r'\n*<image\b[^>]*>\s*</image>\s*$', '',s).strip()
        if any(m['role']==role and mirror_text(m['text'])==mirror_text(body) and abs(m['source_line']-ln)<10 for m in messages):continue
        question_mirror=next((m for m in messages if role=='assistant' and m['role']=='assistant_question' and abs(m['source_line']-ln)<10 and any(body==q['title'] or body.startswith(q['title']+'\n') for q in m['original_question_arguments'].get('questions',[]))),None)
        if question_mirror:
            # Prefer the exact visible question rendering, retaining original structured arguments too.
            question_mirror['text']=body;question_mirror['text_sha256']=sha(body.encode('utf8'));question_mirror['visible_source_line']=ln
            continue
        if body:
            messages.append({'source_line':ln,'source_type':'item_completed/display_fallback','id':item.get('id'),
                             'timestamp_utc':r['timestamp'],'timestamp_beijing':local_time(r['timestamp']),
                             'role':role,'phase':item.get('phase'),'text':body,'text_sha256':sha(body.encode()),'attachments':[]})
            fallbacks+=1
    messages.sort(key=lambda m:m['source_line'])
    user_number=0
    for n,m in enumerate(messages,1):
        m['archive_id']=f'D{n:03}'
        if m['role']=='user':user_number+=1;m['prompt_id']=f'U{user_number:02}'
    stats=collections.Counter(m['role'] for m in messages)
    meta={'title':TITLE,'created_date_beijing':'2026-11-13','timezone':'Asia/Shanghai',
          'source_session':str(SESSION),'session_id':'01a1c98f-c2e0-7e42-a0d0-3e68bc871e53',
          'source_file_snapshot_bytes':len(raw),'source_file_snapshot_sha256':sha(raw),
          'source_prefix_through_cutoff_sha256':sha(b'\n'.join(raw.splitlines()[:cutoff])),
          'cutoff_source_line':cutoff,'cutoff_text':messages[-1]['text'],
          'first_timestamp':messages[0]['timestamp_beijing'],'last_timestamp':messages[-1]['timestamp_beijing'],
          'counts':dict(stats),'total_messages':len(messages),'display_fallbacks':fallbacks,
          'excluded':dict(excluded),'attachments':attachments,
          'scope':'用户消息、对外进度/最终回复及可见交互问题；不含系统/开发者提示、工具执行日志、内部推理或压缩交接摘要。',
          'original_text_policy':'逐条文本不改写、不去尾部换行；补充编号、时间和来源行；图片单独恢复。异步确认保留原记录封装。',
          'cutoff_policy':'归档到用户本次完整整理请求（含上一条被中断请求）；不把本次整理过程自身递归收入。',
          'limitations':['仅归档这条已定位的本地会话；不声称包含其他聊天或语音原始录音。','用户异步确认的原始记录包含界面封装；展示另作说明，未改写原始字段。','原始回复中的绝对链接保留；便携副本以本档案附件路径为准。','原始日志是持续追加文件；完整文件哈希对应导出时快照，截断前缀哈希用于稳定核对。']}
    dump('原始记录/对话原文.json',messages);dump('原始记录/用户原始提示词.json',[m for m in messages if m['role']=='user'])
    dump('归档说明.json',meta)
    return messages,meta

def fenced(s):
    runs=[len(x) for x in re.findall(r'`+',s)];f='`'*max(4,max(runs,default=0)+1)
    return f+'text\n'+s+('' if s.endswith('\n') else '\n')+f+'\n'
def message_md(m):
    role={'user':'用户原文','assistant':'助手回复','assistant_question':'助手交互问题'}[m['role']]
    pid=' / '+m['prompt_id'] if 'prompt_id' in m else ''
    s=f"### {m['archive_id']}{pid} · {role} · {m['timestamp_beijing']}\n\n"
    s+=f"记录类型：{m.get('phase') or 'user'}；原始会话行：{m['source_line']}。\n\n"+fenced(m['text'])+'\n'
    for a in m['attachments']:s+=f"![用户原始参考图]({a['path']})\n\n"
    return s

def bundle():
    paths=[]
    for folder,extensions in [
        ('Research/Step1',{'.md'}),('Research/Step2',{'.md'}),
        ('Research/Step2/Engineering',{'.md','.py','.json','.csv','.html'}),
        ('Research/Step3',{'.md','.py','.mjs','.json','.csv','.html','.svg','.png'}),
        ('Tools/UnrealMCP',{'.md','.py'}),('Tools/BossLab',{'.md','.py'})]:
        for p in (ROOT/folder).iterdir():
            if p.is_file() and p.suffix in extensions and p.name not in ('archive_narrative.md','build_archive.py'):paths.append(p)
    paths.extend(ROOT/p for p in ['Content/Python/init_unreal.py','Saved/UnrealMCP/blueprint_probe.json',
        'Saved/BossImplementation/blueprint_build.json','Saved/BossImplementation/scene_build.json',
        'Saved/BossImplementation/runtime_verification.json','Saved/BossImplementation/learning_verification.json'])
    index=[]
    for p in paths:
        if not p.exists():continue
        rel=p.relative_to(ROOT);dest=OUT/'参考附件'/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
        index.append({'source_project_path':rel.as_posix(),'archive_path':dest.relative_to(OUT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())})
    for source,name in [('Saved/Screenshots/WindowsEditor/BossLab_Final.png','UE白盒运行截图.png'),('Research/Step3/Boss全量分层状态机总览.png','状态机全图预览.png')]:
        p=ROOT/source
        if p.exists():
            (OUT/'图片').mkdir(exist_ok=True);shutil.copy2(p,OUT/'图片'/name)
    conf=tomllib.loads(Path('C:/Users/Lenovo/.codex/config.toml').read_text(encoding='utf8'))['mcp_servers']['unreal_project']
    dump('配置快照/unreal_project.json',conf)
    toml='[mcp_servers.unreal_project]\ncommand = '+json.dumps(conf['command'],ensure_ascii=False)+'\nargs = [\n'+''.join('  '+json.dumps(a,ensure_ascii=False)+',\n' for a in conf['args'])+']\n'
    for k in ('enabled','startup_timeout_sec','tool_timeout_sec'):
        if k in conf:toml+=k+' = '+json.dumps(conf[k])+'\n'
    write('配置快照/unreal_project.toml',toml)
    # Official docs fetch was denied. This note prevents a local recollection becoming a false citation.
    write('配置快照/配置来源说明.txt','此处仅提取 Codex config.toml 中 unreal_project 服务段。\n未复制其他服务、账户或凭据配置。\n本机配置与现有桥接脚本是过程复盘依据。\n2026-11-13 尝试访问 https://developers.openai.com/codex/mcp/ 和 config-reference 页面均返回 HTTP 403，未据此页面作已核实断言。\n')
    dump('参考附件索引.json',index)
    return index

def blocks(md):
    lines=md.splitlines();i=0
    while i<len(lines):
        l=lines[i]
        if not l.strip():i+=1;continue
        f=re.match(r'^(`{3,})(.*)$',l)
        if f:
            fence=f[1];code=[];i+=1
            while i<len(lines) and not lines[i].startswith(fence):code.append(lines[i]);i+=1
            yield ('code',f[2], '\n'.join(code));i+=1;continue
        h=re.match(r'^(#{1,6})\s+(.*)',l)
        if h:yield ('heading',len(h[1]),h[2]);i+=1;continue
        if l.startswith('|') and i+1<len(lines) and re.match(r'^\|[\s:|\-]+\|$',lines[i+1]):
            rows=[[v.strip() for v in l.strip('|').split('|')]];i+=2
            while i<len(lines) and lines[i].startswith('|'):rows.append([v.strip() for v in lines[i].strip('|').split('|')]);i+=1
            yield ('table',rows);continue
        im=re.match(r'^!\[([^]]*)\]\(([^)]+)\)$',l)
        if im:yield ('image',im[1],im[2]);i+=1;continue
        if re.match(r'^[-*]\s',l) or re.match(r'^\d+\.\s',l):yield ('list',l);i+=1;continue
        para=[l];i+=1
        while i<len(lines) and lines[i].strip() and not re.match(r'^(#{1,6} |```|\||!\[|[-*] |\d+\. )',lines[i]):para.append(lines[i]);i+=1
        yield ('paragraph','\n'.join(para))

def inline(s):
    # Escape text before applying a deliberately small Markdown subset.
    s=html.escape(s)
    s=re.sub(r'`([^`]+)`',lambda m:'<code>'+m[1]+'</code>',s)
    s=re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',s)
    s=re.sub(r'\[([^]]+)\]\(([^)]+)\)',r'<a href="\2">\1</a>',s)
    return s

def render_html(md):
    out=[]
    for b in blocks(md):
        if b[0]=='heading':out.append(f'<h{b[1]}>{inline(b[2])}</h{b[1]}>')
        elif b[0]=='code':out.append('<pre class="code">'+html.escape(b[2])+'</pre>')
        elif b[0]=='table':out.append('<div class="table"><table>'+''.join('<tr>'+''.join(('<th>' if j==0 else '<td>')+inline(v)+('</th>' if j==0 else '</td>') for v in row)+'</tr>' for j,row in enumerate(b[1]))+'</table></div>')
        elif b[0]=='image':out.append('<figure><img src="'+html.escape(b[2],quote=True)+'" alt="'+html.escape(b[1],quote=True)+'"><figcaption>'+html.escape(b[1])+'</figcaption></figure>')
        elif b[0]=='list':out.append('<p class="list">'+inline(b[1])+'</p>')
        else:out.append('<p>'+inline(b[1])+'</p>')
    return '\n'.join(out)

def html_document(narrative,messages,meta):
    cards=[]
    for m in messages:
        role={'user':'用户','assistant':'助手','assistant_question':'交互问题'}[m['role']]
        extra=' / '+m['prompt_id'] if m.get('prompt_id') else ''
        card=f'<details class="message {m["role"]}"><summary><b>{m["archive_id"]}{extra} · {role}</b><time>{m["timestamp_beijing"]}</time><span>{html.escape(m["text"][:110])}</span></summary>'
        card+=f'<small>原始记录行 {m["source_line"]} · {html.escape(m.get("phase") or "user")}</small><pre class="original">{html.escape(m["text"])}</pre>'
        for a in m['attachments']:card+='<a href="'+a['path']+'"><img loading="lazy" src="'+a['path']+'" alt="用户原始参考图"></a>'
        cards.append(card+'</details>')
    css='''
:root{color-scheme:light;--ink:#19283a;--line:#dce4ed;--accent:#176f87}*{box-sizing:border-box}body{margin:0;color:var(--ink);background:#f3f6fa;font:16px/1.8 system-ui,"Microsoft YaHei",sans-serif}header{background:#13283b;color:white;padding:42px max(24px,calc((100vw - 1120px)/2));}header h1{font-size:30px;color:white}header p{color:#c6dce4}nav{position:sticky;top:0;background:#fffffff5;border-bottom:1px solid var(--line);padding:12px 24px;display:flex;gap:20px;z-index:2;flex-wrap:wrap}nav a{color:var(--accent)}main{max-width:1168px;margin:auto;padding:24px}article,section{background:white;border:1px solid var(--line);border-radius:12px;padding:32px;margin-bottom:24px}h1,h2,h3{line-height:1.5;color:#153e55}h2{border-bottom:2px solid #d7e5ec;padding-bottom:10px;margin-top:40px}h3{margin-top:28px}p{margin:14px 0}.code{background:#10283b;color:#e2f2f4;padding:18px;border-radius:7px;white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.7 Consolas,"Microsoft YaHei",monospace}code{background:#eaf1f6;padding:2px 4px;border-radius:3px;overflow-wrap:anywhere}.table{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{border:1px solid var(--line);padding:10px;text-align:left;vertical-align:top}th{background:#eaf3f6}img{max-width:100%;height:auto;border-radius:6px}figure{margin:24px 0}figcaption{color:#627488;font-size:13px}.message{border:1px solid var(--line);border-left:4px solid #91a5b5;border-radius:6px;margin:12px 0;padding:12px 16px}.message.user{border-left-color:#d99327;background:#fffdf7}.message.assistant_question{border-left-color:#9279b5}summary{cursor:pointer}summary span{display:block;color:#607388;font-size:13px;white-space:pre-wrap;overflow-wrap:anywhere}time{float:right;color:#677c8b;font-size:13px}.original{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.8 Consolas,"Microsoft YaHei",monospace;margin:16px 0}.toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center}input{min-width:250px;flex:1;padding:10px;border:1px solid #a6bac9;border-radius:5px}button{padding:10px;border:1px solid #a6bac9;background:#f0f6fa;border-radius:5px;cursor:pointer}small{color:#5c7180}a{color:#176d93} @media print{nav,.toolbar{display:none}header{background:white;color:black;padding:0}header h1,header p{color:black}body{background:white;font-size:10pt}main{padding:0}article,section{border:0;padding:0}details>summary{display:block}details>.original{display:block!important}pre{white-space:pre-wrap}h2,h3{break-after:avoid}tr,img{break-inside:avoid}}
'''
    js='''const cards=[...document.querySelectorAll('.message')];const q=document.getElementById('query');q.addEventListener('input',()=>{let n=0;const s=q.value.toLowerCase();for(const c of cards){const match=c.textContent.toLowerCase().includes(s);c.hidden=!match;if(s&&match)c.open=true;if(match)n++;}document.getElementById('hits').textContent=n+' 条';});document.getElementById('expand').onclick=()=>cards.forEach(c=>c.open=true);document.getElementById('collapse').onclick=()=>cards.forEach(c=>c.open=false);window.addEventListener('beforeprint',()=>cards.forEach(c=>c.open=true));'''
    return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+TITLE+'</title><style>'+css+'</style></head><body><header><h1>'+TITLE+'</h1><p>项目档案 · 2026-11-13 · UE 5.8.4 · 原始记录与复盘分别保存</p></header><nav><a href="#guide">项目过程与通用流程</a><a href="#dialogue">原始对话</a><a href="用户原始提示词.md">原始提示词</a><a href="'+TITLE+'.docx">Word 版本</a><a href="参考附件/Research/Step3/Boss全量分层状态机.html">交互状态图</a></nav><main><article id="guide">'+render_html(narrative)+'</article><section id="dialogue"><h2>附录：原始对话</h2><p>以下正文保持原文；编号、时间、角色标记为归档添加。所有时间为北京时间。共 '+str(meta['total_messages'])+' 条记录。</p><div class="toolbar"><input id="query" aria-label="搜索原始对话" placeholder="搜索原始对话、招式编号或提示词"><button id="expand">全部展开</button><button id="collapse">全部收起</button><span id="hits">'+str(len(messages))+' 条</span></div>'+''.join(cards)+'</section></main><script>'+js+'</script></body></html>'

# Small standard-library Word exporter. No macros, external templates or dependencies.
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
NS={'w':W,'r':R,'wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing','a':'http://schemas.openxmlformats.org/drawingml/2006/main','pic':'http://schemas.openxmlformats.org/drawingml/2006/picture'}
for k,v in NS.items():ET.register_namespace(k,v)
def el(parent,tag,attrs=None,text=None):
    ns,local=tag.split(':');e=ET.SubElement(parent,'{'+NS[ns]+'}'+local,{'{'+NS[k.split(':')[0]]+'}'+k.split(':')[1]:str(v) for k,v in (attrs or {}).items()} if attrs else {})
    if text is not None:e.text=text
    return e
def para(parent,text,style=None):
    p=el(parent,'w:p')
    if style:el(el(p,'w:pPr'),'w:pStyle',{'w:val':style})
    for i,line in enumerate(text.split('\n')):
        r=el(p,'w:r')
        if i:el(r,'w:br')
        t=el(r,'w:t',text=line);t.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
    return p
def xml(e):return ET.tostring(e,encoding='utf-8',xml_declaration=True)
def plain(s):return re.sub(r'`([^`]+)`',r'\1',re.sub(r'\*\*([^*]+)\*\*',r'\1',s))

def make_docx(narrative,messages,meta):
    root=ET.Element('{'+W+'}document');body=el(root,'w:body');media=[]
    def picture(path,alt):
        p=OUT/path
        if not p.exists() or p.suffix.lower()!='.png':return
        raw=p.read_bytes();width,height=struct.unpack('>II',raw[16:24]);cx=5500000;cy=int(cx*height/width)
        if cy>7000000:cx=int(cx*7000000/cy);cy=7000000
        idx=len(media)+1;rid=f'rIdImage{idx}';media.append((rid,p,raw))
        par=el(body,'w:p');drawing=el(el(par,'w:r'),'w:drawing');inline_=el(drawing,'wp:inline')
        ET.SubElement(inline_,'{'+NS['wp']+'}extent',{'cx':str(cx),'cy':str(cy)})
        ET.SubElement(inline_,'{'+NS['wp']+'}docPr',{'id':str(idx),'name':alt})
        gr=el(inline_,'a:graphic');data=ET.SubElement(gr,'{'+NS['a']+'}graphicData',{'uri':NS['pic']});pic=el(data,'pic:pic')
        nv=el(pic,'pic:nvPicPr');ET.SubElement(nv,'{'+NS['pic']+'}cNvPr',{'id':'0','name':p.name});el(nv,'pic:cNvPicPr')
        fill=el(pic,'pic:blipFill');el(fill,'a:blip',{'r:embed':rid});el(el(fill,'a:stretch'),'a:fillRect')
        sp=el(pic,'pic:spPr');xf=el(sp,'a:xfrm');ET.SubElement(xf,'{'+NS['a']+'}off',{'x':'0','y':'0'});ET.SubElement(xf,'{'+NS['a']+'}ext',{'cx':str(cx),'cy':str(cy)})
        geo=ET.SubElement(sp,'{'+NS['a']+'}prstGeom',{'prst':'rect'});el(geo,'a:avLst');para(body,alt,'Caption')
    for b in blocks(narrative):
        if b[0]=='heading':para(body,plain(b[2]),'Title' if b[1]==1 else 'Heading'+str(min(b[1]-1,3)))
        elif b[0]=='table':
            table=el(body,'w:tbl');props=el(table,'w:tblPr');borders=el(props,'w:tblBorders')
            for side in ['top','left','bottom','right','insideH','insideV']:el(borders,'w:'+side,{'w:val':'single','w:sz':'4','w:color':'C7D6E2'})
            for j,row in enumerate(b[1]):
                tr=el(table,'w:tr')
                for value in row:
                    tc=el(tr,'w:tc');para(tc,plain(value),'TableHeader' if j==0 else 'TableText')
            para(body,'')
        elif b[0]=='code':
            for line in b[2].split('\n'):para(body,line,'Code')
        elif b[0]=='image':picture(b[2],b[1])
        else:para(body,plain(b[1]))
    para(body,'附录：原始对话（逐条原文）','Heading1')
    para(body,f"范围：{meta['first_timestamp']} 至 {meta['last_timestamp']}，北京时间。原文不修订；标签与来源行为归档补充。")
    for m in messages:
        role={'user':'用户原文','assistant':'助手回复','assistant_question':'助手交互问题'}[m['role']]
        para(body,m['archive_id']+(' / '+m['prompt_id'] if m.get('prompt_id') else '')+' · '+role+' · '+m['timestamp_beijing'],'Heading2')
        para(body,f"来源行 {m['source_line']}；类型 {m.get('phase') or 'user'}。",'Caption')
        for line in m['text'].split('\n'):para(body,line,'Transcript')
        for a in m['attachments']:picture(a['path'],'用户原始参考图，按原始消息恢复')
    sect=el(body,'w:sectPr');el(sect,'w:pgSz',{'w:w':'11906','w:h':'16838'});el(sect,'w:pgMar',{'w:top':'1080','w:right':'1000','w:bottom':'1080','w:left':'1000','w:header':'500','w:footer':'500','w:gutter':'0'})
    styles=ET.Element('{'+W+'}styles');default=el(styles,'w:docDefaults');rp=el(el(default,'w:rPrDefault'),'w:rPr');el(rp,'w:rFonts',{'w:ascii':'Calibri','w:hAnsi':'Calibri','w:eastAsia':'Microsoft YaHei'});el(rp,'w:sz',{'w:val':'21'});el(rp,'w:lang',{'w:val':'zh-CN','w:eastAsia':'zh-CN'})
    pp=el(el(default,'w:pPrDefault'),'w:pPr');el(pp,'w:spacing',{'w:after':'120','w:line':'310','w:lineRule':'auto'})
    for name,size,color in [('Title',36,'123D55'),('Heading1',29,'123D55'),('Heading2',24,'176F87'),('Heading3',22,'176F87'),('Code',17,'30465A'),('Transcript',20,'24374A'),('Caption',18,'647B8C'),('TableHeader',19,'123D55'),('TableText',19,'24374A')]:
        st=el(styles,'w:style',{'w:type':'paragraph','w:styleId':name});el(st,'w:name',{'w:val':name});rp=el(st,'w:rPr');el(rp,'w:sz',{'w:val':size});el(rp,'w:color',{'w:val':color});pp=el(st,'w:pPr')
        if name.startswith('Heading') or name in ('Title','TableHeader'):el(rp,'w:b');el(pp,'w:keepNext')
        if name.startswith('Heading'):el(pp,'w:outlineLvl',{'w:val':int(name[-1])-1})
        if name=='Code':el(rp,'w:rFonts',{'w:ascii':'Consolas','w:hAnsi':'Consolas','w:eastAsia':'Microsoft YaHei'});el(pp,'w:shd',{'w:fill':'EEF3F7'});el(pp,'w:spacing',{'w:after':'30'})
    relns='http://schemas.openxmlformats.org/package/2006/relationships';rels=ET.Element('Relationships',xmlns=relns)
    ET.SubElement(rels,'Relationship',Id='rIdStyles',Type=R+'/styles',Target='styles.xml')
    for i,(rid,p,_) in enumerate(media,1):ET.SubElement(rels,'Relationship',Id=rid,Type=R+'/image',Target=f'media/image{i}.png')
    content=ET.Element('Types',xmlns='http://schemas.openxmlformats.org/package/2006/content-types')
    for ext,mime in [('rels','application/vnd.openxmlformats-package.relationships+xml'),('xml','application/xml'),('png','image/png')]:ET.SubElement(content,'Default',Extension=ext,ContentType=mime)
    for part,mime in [('/word/document.xml','application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'),('/word/styles.xml','application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml')]:ET.SubElement(content,'Override',PartName=part,ContentType=mime)
    package=ET.Element('Relationships',xmlns=relns);ET.SubElement(package,'Relationship',Id='rId1',Type=R+'/officeDocument',Target='word/document.xml')
    with zipfile.ZipFile(OUT/(TITLE+'.docx'),'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in [('word/document.xml',xml(root)),('word/styles.xml',xml(styles)),('word/_rels/document.xml.rels',xml(rels)),('[Content_Types].xml',xml(content)),('_rels/.rels',xml(package))]:z.writestr(name,data)
        for i,(_,p,data) in enumerate(media,1):z.writestr(f'word/media/image{i}.png',data)

def validate(messages,meta):
    exported=json.loads((OUT/'原始记录/对话原文.json').read_text(encoding='utf8'))
    source={i:json.loads(l) for i,l in enumerate(SESSION.read_text(encoding='utf8').splitlines(),1) if i<=meta['cutoff_source_line']}
    for m in exported:
        assert sha(m['text'].encode())==m['text_sha256']
        if m['source_type']=='response_item/message':assert m['text']==text_content(source[m['source_line']]['payload'])
        for a in m['attachments']:assert sha((OUT/a['path']).read_bytes())==a['sha256']
    assert sum(m['role']=='user' for m in messages)==len(json.loads((OUT/'原始记录/用户原始提示词.json').read_text(encoding='utf8')))
    assert not any('Another language model started to solve' in m['text'] for m in messages)
    assert messages[-1]['role']=='user' and CUTOFF in messages[-1]['text']
    with zipfile.ZipFile(OUT/(TITLE+'.docx')) as z:
        assert z.testzip() is None
        for n in z.namelist():
            if n.endswith(('.xml','.rels')):ET.fromstring(z.read(n))
        document=ET.fromstring(z.read('word/document.xml'));texts=[e.text or '' for e in document.iter('{'+W+'}t')]
        assert all(m['archive_id'] in '\n'.join(texts) for m in messages)
    page=(OUT/(TITLE+'.html')).read_text(encoding='utf8')
    for m in messages:assert html.escape(m['text']) in page
    checks={'message_texts_match_source':True,'message_hashes_valid':True,'attachments_match_source':True,'prompt_count_consistent':True,
            'compaction_summaries_excluded':True,'docx_zip_and_xml_valid':True,'docx_all_message_labels_present':True,'html_all_original_texts_present':True,
            'total_messages':len(messages),'user_messages':meta['counts']['user'],'word_visual_layout_reviewed':False}
    dump('文档校验报告.json',checks)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    messages,meta=extract();files=bundle()
    narrative=(ROOT/'Tools/BossLab/archive_narrative.md').read_text(encoding='utf8')
    coverage=f"\n归档核对：共 {len(messages)} 条，包括用户 {meta['counts'].get('user',0)} 条、助手回复 {meta['counts'].get('assistant',0)} 条、可见交互问题 {meta['counts'].get('assistant_question',0)} 条。已排除 {meta['excluded'].get('compaction_summaries',0)} 条自动上下文交接摘要。用户原始参考图已从会话图像数据恢复。\n\n"
    narrative=narrative.replace('## 1. 阅读与文件说明',coverage+'## 1. 阅读与文件说明',1)
    visuals='\n## 9. 项目图示\n\n'
    for name,label in [('用户原始参考图_1.png','用户提供的状态机参考截图（原始附件）'),('状态机全图预览.png','第三步生成的全量状态机概览'),('UE白盒运行截图.png','开发阶段保存的 UE 双 Boss 白盒运行画面')]:
        if (OUT/'图片'/name).exists():visuals+=f'![{label}](图片/{name})\n\n'
    narrative+=visuals
    transcript='# 原始对话逐条归档\n\n正文保持原文；仅添加时间、角色、来源行和编号。Markdown／链接文字作为原文保留。时区：Asia/Shanghai。\n\n'+''.join(message_md(m) for m in messages)
    prompts='# 用户原始提示词与确认记录\n\n本文件逐条保留用户消息，包括原始报错、规则补充、异步确认和被中断的整理请求。模板另见总文档，不混入原话。\n\n'
    prompts+='| 提示词 | 北京时间 | 原文开头 |\n|---|---|---|\n'
    for m in messages:
        if m['role']=='user':prompts+=f"| {m['prompt_id']} | {m['timestamp_beijing']} | {m['text'][:55].replace(chr(10),' ').replace('|',' / ')} |\n"
    prompts+='\n'+''.join(message_md(m) for m in messages if m['role']=='user')
    write('原始对话.md',transcript);write('用户原始提示词.md',prompts)
    master=narrative+'\n# 附录：原始对话（逐条原文）\n\n'+transcript.split('\n',1)[1]
    write(TITLE+'.md',master);write(TITLE+'.html',html_document(narrative,messages,meta));make_docx(narrative,messages,meta)
    write('00_阅读入口.md',f'''# 影之刃零复刻项目档案

建议先打开 [{TITLE}.html]({TITLE}.html)：包含项目全流程、MCP 配置排错、可复用提示词模板及可搜索原始对话。

- [{TITLE}.docx]({TITLE}.docx)：Word 版，包含同一正文及原始对话，支持批注和打印。
- [{TITLE}.pdf]({TITLE}.pdf)：同内容的打印版，所有对话已展开。
- [{TITLE}.md]({TITLE}.md)：完整可编辑文本。
- [用户原始提示词.md](用户原始提示词.md)：{meta['counts']['user']} 条用户原文单独汇总。
- [原始对话.md](原始对话.md)：{meta['total_messages']} 条对话／交互问题，保留时间与来源。
- 原始记录：逐条 JSON，含文本校验值；没有系统提示或内部推理。
- 配置快照：仅 unreal_project 服务段，以及来源说明。
- 参考附件：{len(files)} 份项目材料，保留原相对路径；可直接打开状态图和概率检查器。
- 图片：原始参考图、状态机概览、UE 运行截图。
- 归档说明.json、文档校验报告.json、文件校验清单.json：来源、范围、原文校验与文件清单。

整理截至 2026-11-13 的本次完整文档请求。档案是文档包，不包含 UE 引擎和 .uasset 工程包。

原始对话保留历史错误和后来修正；当前实现边界以总文档第 5 节为准。43 项 UE 检查是开发阶段的历史报告，本次仅归档，不宣称重新运行或完成原设计全部执行节点。
''')
    validate(messages,meta)
    manifest=[]
    for p in sorted(OUT.rglob('*')):
        if p.is_file() and p.name!='文件校验清单.json':manifest.append({'path':p.relative_to(OUT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())})
    dump('文件校验清单.json',manifest)
    print(json.dumps({'folder':str(OUT),'messages':meta['counts'],'total':len(messages),'excluded':meta['excluded'],'source_cutoff':meta['cutoff_source_line'],'attachments':len(meta['attachments']),'reference_files':len(files),'files':len(manifest)+1,'docx_bytes':(OUT/(TITLE+'.docx')).stat().st_size},ensure_ascii=False))

if __name__=='__main__':main()
