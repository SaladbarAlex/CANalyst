from pathlib import Path
import re, html
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Image, KeepTogether, CondPageBreak
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
ROOT=Path.cwd(); OUT=ROOT/'output/pdf/CANalyst_Changes_and_Remaining_Work_2026-10-30.pdf'
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='BodyR',fontName='Helvetica',fontSize=9.3,leading=13.4,spaceAfter=7,textColor=colors.HexColor('#24333c')))
styles.add(ParagraphStyle(name='SmallR',fontName='Helvetica',fontSize=7.1,leading=9.5,spaceAfter=3,wordWrap='CJK'))
styles.add(ParagraphStyle(name='CodeR',fontName='Courier',fontSize=7,leading=10,spaceAfter=7,wordWrap='CJK',backColor=colors.HexColor('#f0f4f6')))
for n in ['Heading1','Heading2','Heading3']:
 styles[n].textColor=colors.HexColor('#155c63');styles[n].spaceBefore=13;styles[n].spaceAfter=8;styles[n].keepWithNext=True
styles['Title'].fontSize=30; styles['Title'].leading=35;styles['Title'].textColor=colors.HexColor('#153e48')
story=[]
def inline(s):
 s=s.replace('—',' - ').replace('–','-').replace('’',"'").replace('“','"').replace('”','"').replace('→',' to ').replace('≤','<=').replace('≥','>=')
 s=re.sub(r'\[([^\]]+)\]\((?:<[^>]+>|[^)]+)\)',r'\1',s)
 s=html.escape(s)
 s=re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',s)
 s=re.sub(r'`([^`]+)`',r'<font name="Courier">\1</font>',s)
 return s

def p(s,style='BodyR'): story.append(Paragraph(inline(s),styles[style]))
def table(rows):
 if story and isinstance(story[-1],Paragraph) and story[-1].style.name.startswith('Heading'):
  story[-1].style=ParagraphStyle(name='TableHeading',parent=story[-1].style,keepWithNext=False)
  story.insert(len(story)-1,CondPageBreak(105))
 n=len(rows[0]); width=504
 if n==2: widths=[width*.31,width*.69]
 elif n==3: widths=[width*.18,width*.36,width*.46]
 else: widths=[width/n]*n
 header=ParagraphStyle(name='HeaderCell',parent=styles['SmallR'],textColor=colors.white,fontName='Helvetica-Bold')
 cells=[[Paragraph(inline(c),header if index==0 else styles['SmallR']) for c in row] for index,row in enumerate(rows)]
 t=Table(cells,colWidths=widths,repeatRows=1,hAlign='LEFT')
 t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#155c63')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.HexColor('#edf4f4'),colors.white]),('BOTTOMPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),6),('LINEBELOW',(0,0),(-1,0),.6,colors.HexColor('#155c63'))]))
 for cell in cells[0]: cell.style=ParagraphStyle(name='th',parent=styles['SmallR'],textColor=colors.white,fontName='Helvetica-Bold')
 story.extend([t,Spacer(1,9)])
def md(text):
 lines=text.splitlines();i=0
 while i<len(lines):
  line=lines[i].strip()
  if not line: i+=1;continue
  if line.startswith('```'):
   i+=1;code=[]
   while i<len(lines) and not lines[i].startswith('```'): code.append(lines[i]);i+=1
   story.append(Paragraph('<br/>'.join(inline(c) for c in code),styles['CodeR']));i+=1;continue
  if line.startswith('|'):
   rows=[]
   while i<len(lines) and lines[i].strip().startswith('|'):
    row=[x.strip() for x in lines[i].strip().strip('|').split('|')]
    if not all(re.fullmatch(r'[:\- ]+',c) for c in row):rows.append(row)
    i+=1
   table(rows);continue
  if line.startswith('#'):
   level=len(line)-len(line.lstrip('#'));p(line.lstrip('# '),'Heading1' if level<=2 else 'Heading2');i+=1;continue
  if re.match(r'^[-*] |^\d+\. ',line): p(line);i+=1;continue
  para=[line];i+=1
  while i<len(lines) and lines[i].strip() and not re.match(r'^(#|\||```|[-*] |\d+\. )',lines[i].strip()):para.append(lines[i].strip());i+=1
  p(' '.join(para))
def new():story.append(PageBreak())
p('CANalyst','Title');p('Changes, results, and remaining work','Heading1');p('Technical handoff | October 30, 2026');p('CPSC 8580 - Clemson University');story.append(Spacer(1,15))
p('The dashboard now opens real recorded CAN traffic. The controls audit, model integrations, reproducible benchmarks, and interactive workflow checks are complete for this development prototype. Research validation and deployment work remain.');
table([['Current state','Verified outcome'],['Open the dashboard','http://127.0.0.1:5173 - refresh the page to load real ROAD traffic.'],['Default data','correlated_signal_attack_3.log: 41,829 frames, 16.964 seconds, 105 IDs; separate basic-short ambient baseline and ROAD metadata.'],['Model result','GLM-5.3 matches control attack-label correctness: 69/69 HCRL and 17/20 ROAD. All 100 final requests succeeded.'],['Control improvement','Full HCRL: false-positive windows reduced from 65 to 28, with unchanged true positives and misses.'],['Verification','101 backend tests; 21 frontend tests; production build; 17 browser workflow checks plus real-default startup/cache verification.'],['Delivery state','Local development servers running; changes uncommitted. Original midterm paper, slides, and historical experiment files preserved.']])
p('Reading guide','Heading2');p('The opening pages explain how to use the real-data dashboard and what to do next. The technical record then inventories all changes, model runs, negative results, provenance, efficiency measurements, and verification. The controls appendix supplies the detailed defect audit and reproduction commands.')
p('Interpretation boundary','Heading2');p('Accuracy parity is observed on detector-selected development alerts. It does not establish unseen-data performance, semantic faithfulness, equivalence at control latency, or improved analyst productivity. Valid citations are references, not proof that a claim follows from them.')
new();p('Review the real-data dashboard','Heading1');p('Open http://127.0.0.1:5173 and refresh. The first request analyzes the installed ROAD files; subsequent loads reuse the in-memory result. The source label identifies the real recording and the baseline label says separate capture. This is a live analysis of one capture, not the aggregate benchmark.')
if (ROOT/'output/pdf/dashboard-real-data.png').exists():story.append(Image(str(ROOT/'output/pdf/dashboard-real-data.png'),width=504,height=367.5))
p('Current dashboard after loading the real ROAD capture. Screenshot captured during this handoff.','SmallR')
p('Inspect the flagged interval, select evidence citations, and compare rate and detector score. The offline control is immediately available. Select GLM or Gemma and press Explain for an explicit hosted request. Benchmark opens the saved multi-capture detection and model comparisons without generating new requests.')
p('Capture settings still accepts your own CSV/candump/HCRL logs, a separate normal baseline, and ROAD metadata. Synthetic traffic remains available through Generate demo traffic or http://127.0.0.1:5173/?dataset=synthetic. Missing ROAD files produce a visible error rather than silently substituting synthetic data.')
p('The default example uses the rule detector, 0.5-second windows, 0.25-second stride, and threshold 0.55. It contains one detected alert; window precision is 1.000 and recall is 0.9216. Those figures describe this recording only. Restarting the API clears in-memory analyses and cached explanations.')
new();p('Remaining work, in priority order','Heading1')
table([['Priority / owner','Work and completion criterion'],['1. Research team - validation design','Reserve untouched tuning/validation/test captures before additional tuning. Split by recording/vehicle and account for correlated overlapping windows. Freeze selection and metrics before examining final labels.'],['2. Detection research','Address weak ROAD masquerade recall and benign operating-state false alarms. Test conditional per-ID/byte or state-based calibration on the reserved split. Promote a detector only if predefined recall/FPR criteria improve; current Forest and broader-baseline results do not justify replacement.'],['3. Explanation quality','Independently adjudicate sampled claims, summaries, recommendations, identifiers and measurement associations. Report supported/unsupported/contradicted claims and inter-rater agreement. Identifier and citation checks cover only part of factual correctness.'],['4. Controlled model comparisons','Run predeclared ablations for evidence/count corrections, rate semantics, replay wording and GLM reasoning settings. Repeat latency measurements under comparable service load. Keep failed attempts, token use, actual served model and exact corpus identity.'],['5. Analyst evaluation','Measure investigation time, classification correctness, evidence-navigation success and confidence with analysts/students under an appropriate study design. Compare control-only and model-assisted workflows. No present artifact proves analyst benefit.'],['6. Performance engineering','Profile feature extraction, optimize large-file ingest and cold ID loading, and measure browser/network latency and concurrent users. Split the frontend bundle (current production build warns above 500 KB). Preserve measurement semantics during optimization.'],['7. Deployment, if requested','Design persistent analyses/jobs, authentication and access control, upload/storage limits, job cancellation, retention, monitoring and secret management. Validate deployment separately; the current local in-memory demo is not a production service.'],['8. Course deliverables / reproducibility','Update the final paper and presentation with v4/control-v5 results, negative experiments and limitations. Pin/review dependencies and dataset manifests, review the working tree, then commit or publish through the normal project process. The original midterm documents were intentionally not rewritten.']])
p('No additional normal-data download was needed: twelve ROAD ambient recordings already existed and were used across baseline/holdout experiments. More normal traffic alone did not solve the observed operating-state problem. New data should follow the evaluation design, rather than be used for opportunistic tuning.')
new();p('Detailed technical record','Title');p('The following record preserves the distinction between historical v2/v3 experiments and the final v4 evidence/control-v5 comparison. Earlier runs are retained for traceability, not blended into the final result. File paths are relative to the CANalyst repository unless stated otherwise.')
log=(ROOT/'docs/PROGRESS_2026-10-30.md').read_text()
# Omit browser-tool authorization history; retain all product and verification outcomes.
log='\n\n'.join(block for block in log.split('\n\n') if not block.startswith('The in-app browser remained unavailable'))
md(log.split('## Real-data default and PDF handoff')[0])
new();p('Appendix: controls and detector audit','Title');md((ROOT/'docs/Controls_and_Detection_Audit_2026-10-30.md').read_text())
new();p('Artifact map and reproduction','Heading1');p('Authoritative local records: docs/PROGRESS_2026-10-30.md and docs/Controls_and_Detection_Audit_2026-10-30.md. README.md documents startup, models, uploads and evaluation commands. backend/out/environment_2026-10-30.json records the tested environment.');
for a,b in [('Final inputs','backend/out/frozen_2026-10-30_v4/'),('Final paired comparisons','backend/out/comparisons_v4_2026-10-30_control_v5/'),('Numeric and semantic audits','backend/out/semantic_audit_2026-10-30/'),('Identifier annotations','backend/out/validation_2026-10-30_v4/'),('Full HCRL verification','backend/out/detectors_full_hcrl_2026-10-30/hcrl_full_midterm/'),('Original browser QA','backend/out/browser_qa_2026-10-30/2026-10-30T18-29-11.655Z/'),('Real-default verification','output/pdf/real-data-verification.json'),('Full-size dashboard timing','backend/out/dashboard_hcrl_full_fuzzy_cached_2026-10-30.json')]:p(a+': '+b)
p('External documentation consulted in the project record','Heading2')
for u in ['https://docs.rcd.clemson.edu/llm/usage/api/','https://docs.rcd.clemson.edu/llm/usage/openai_api/','https://docs.rcd.clemson.edu/llm/models/','https://docs.z.ai/guides/capabilities/thinking-mode/']:p(u)
p('This report summarizes repository artifacts and local verification as of October 30, 2026. Service availability and future model catalog changes must be checked separately. No new hosted inference was performed to create this PDF or verify the real-data default.')
def footer(c,d):
 c.saveState();c.setStrokeColor(colors.HexColor('#b4cccd'));c.line(54,42,558,42);c.setFont('Helvetica',8);c.setFillColor(colors.HexColor('#54666d'));c.drawString(54,29,'CANalyst | Technical handoff | 30 October 2026');c.drawRightString(558,29,str(d.page));c.restoreState()
doc=SimpleDocTemplate(str(OUT),pagesize=letter,rightMargin=54,leftMargin=54,topMargin=45,bottomMargin=56,title='CANalyst - Changes and Remaining Work',author='CANalyst project technical review')
doc.build(story,onFirstPage=footer,onLaterPages=footer)
print(OUT)
