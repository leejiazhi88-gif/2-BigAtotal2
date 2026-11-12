import fs from 'node:fs/promises';
import {Workbook, SpreadsheetFile} from '@oai/artifact-tool';
const base = process.cwd();
const source = JSON.parse(await fs.readFile(`${base}/work/bank-table-format/source.json`, 'utf8'));
const data = source.slice(1);
for (const row of data) {
  for (const [pe, pct, samples] of [[5,6,7],[11,12,13]]) {
    row[pct] = String(data.filter(other => Number(other[pe]) <= Number(row[pe])).length / data.length * 100);
    row[samples] = String(data.length);
  }
}
const wb = Workbook.create();
const sh = wb.worksheets.add('季度末对照');
sh.showGridLines = false;
const all = sh.getRange('A1:N52');
all.format.font = {name:'PingFang SC',size:11,color:'#243447'};
all.format.rowHeight = 27;
all.format.columnWidth = 15;
all.format.verticalAlignment='center';
sh.getRange('A:A').format.columnWidth=13;
sh.getRange('B:B').format.columnWidth=16;
sh.getRange('C:C').format.columnWidth=31;
for (const c of ['D','E','J','K']) sh.getRange(`${c}:${c}`).format.columnWidth=20;
sh.mergeCells('A1:N1');
sh.getRange('A1').values=[['银行指数估值｜过去十年季度末口径对照']];
sh.getRange('A1:N1').format.fill='#172D46';
sh.getRange('A1:N1').format.font={name:'PingFang SC',size:20,bold:true,color:'#FFFFFF'};
sh.getRange('A1:N1').format.rowHeight=48;
for (const [r,text] of [
 [2,'2016Q4—2026Q3，共40个季度末交易日。金额单位：亿元；PE单位：倍。'],
 [3,'PE分位：各口径在全部40个季度中，PE不高于该行的季度数÷40，包含该行及并列值。'],
 [4,'申万历史公司数未提供（当前42家仅供参考）；申万TTM利润为总市值÷PE反推值。']
]) { sh.mergeCells(`A${r}:N${r}`); sh.getRange(`A${r}`).values=[[text]]; }
sh.getRange('A2:N4').format.font={name:'PingFang SC',size:11,color:'#596B7E'};
sh.mergeCells('A6:B6'); sh.mergeCells('C6:H6'); sh.mergeCells('I6:N6');
sh.getRange('A6').values=[['采样时点']];
sh.getRange('C6').values=[['2项目 · 申万银行指数（801780.SI）']];
sh.getRange('I6').values=[['2.2项目 · 公司汇总口径']];
sh.getRange('A6:B7').format.fill='#526579';
sh.getRange('C6:H7').format.fill='#235B8C';
sh.getRange('I6:N7').format.fill='#21766D';
sh.getRange('A6:N7').format.font={name:'PingFang SC',size:11,bold:true,color:'#FFFFFF'};
sh.getRange('A6:N7').format.horizontalAlignment='center';
sh.getRange('A6:N7').format.wrapText=true;
sh.getRange('A6:N6').format.rowHeight=34;
sh.getRange('A7:N7').format.rowHeight=46;
sh.getRange('A7:N7').values=[['季度','季度末\n交易日','涵盖公司\n（口径说明）','总市值\n（亿元）','反推TTM利润\n（亿元）','PE\n（倍）','PE历史分位','分位样本\n（季度数）','涵盖公司\n（家）','总市值\n（亿元）','TTM利润\n（亿元）','PE\n（倍）','PE历史分位','分位样本\n（季度数）']];
const rows=source.slice(1).map(r=>r.map((v,i)=>i===0||i===2?v:i===1?new Date(`${v.slice(0,4)}-${v.slice(4,6)}-${v.slice(6,8)}T00:00:00Z`):i===6||i===12?Number(v)/100:Number(v)));
sh.getRange('A8:N47').values=rows;
sh.getRange('B8:B47').setNumberFormat('yyyy-mm-dd');
for(const c of ['D','E','J','K']) sh.getRange(`${c}8:${c}47`).setNumberFormat('#,##0.00');
for(const c of ['F','L']) sh.getRange(`${c}8:${c}47`).setNumberFormat('0.00');
for(const c of ['G','M']) sh.getRange(`${c}8:${c}47`).setNumberFormat('0.0%');
sh.getRange('C8:C47').format.font={name:'PingFang SC',size:10,color:'#596B7E'};
sh.getRange('A8:C47').format.horizontalAlignment='center';
sh.getRange('D8:N47').format.horizontalAlignment='right';
for(let r=8;r<=47;r++) if(r%2===0) sh.getRange(`A${r}:N${r}`).format.fill='#F1F5F9';
sh.getRange('A47:N47').format.fill='#E0EDEB';
sh.getRange('A47:N47').format.font.bold=true;
for(const [r,text] of [
 [49,'2.2口径：以当前42家公司回溯历史，按各公司上市时间纳入。'],
 [50,'来源：原季度对照CSV；申万 sw_daily；2.2项目银行 data.json / company-quarterly.csv。'],
 [51,'分位用于回顾2016Q4—2026Q3的相对高低，包含后续季度数据，不代表当时可获得的历史分位。']
]){sh.mergeCells(`A${r}:N${r}`); sh.getRange(`A${r}`).values=[[text]];}
sh.getRange('A49:N51').format.font={name:'PingFang SC',size:10,color:'#596B7E'};
sh.freezePanes.freezeRows(7); sh.freezePanes.freezeColumns(2);
wb.recalculate();
console.log((await wb.inspect({kind:'table',range:'季度末对照!A6:N9',include:'values',tableMaxRows:4,tableMaxCols:14})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!',options:{useRegex:true,maxResults:20}})).ndjson);
const preview=await wb.render({sheetName:'季度末对照',range:'A1:N12',scale:1,format:'png'});
await fs.writeFile(`${base}/work/bank-table-format/preview.png`,new Uint8Array(await preview.arrayBuffer()));
const out=await SpreadsheetFile.exportXlsx(wb);
await out.save(`${base}/outputs/bank-pe-comparison/银行PE季度末对照.xlsx`);
const headers=['季度','季度末交易日','申万-涵盖公司说明','申万-总市值（亿元）','申万-反推TTM利润（亿元）','申万-PE（倍）','申万-PE分位（%）','申万-分位样本（季度数）','2.2-涵盖公司（家）','2.2-总市值（亿元）','2.2-TTM利润（亿元）','2.2-PE（倍）','2.2-PE分位（%）','2.2-分位样本（季度数）'];
const csv=[headers,...source.slice(1).map(r=>r.map((v,i)=>i===1?`${v.slice(0,4)}-${v.slice(4,6)}-${v.slice(6,8)}`:v))].map(r=>r.map(v=>'"'+String(v).replaceAll('"','""')+'"').join(',')).join('\r\n')+'\r\n';
await fs.writeFile(`${base}/outputs/bank_pe_10y_quarterly_comparison.csv`,'\uFEFF'+csv,'utf8');
const intro='# 银行 PE 十年季度末口径对照\n\n区间为2016Q4—2026Q3，共40个共同季度；每季度取最后交易日。市值和利润单位为亿元，PE单位为倍。\n\n**统一40季排名**：各口径分别计算，PE分位＝全部40个季度中PE不高于该行的季度数÷40，包含自身及并列值。每行样本数均为40。用于回顾区间内的相对高低，包含后续数据，不代表历史时点当时可获得的分位。\n\n申万口径：Tushare `sw_daily` 银行指数801780.SI，总市值÷PE反推TTM利润。接口不提供历史公司数，当前42家仅供参考。2.2口径：当前42家银行按上市时间纳入历史，市值加总÷公司公告/重建TTM归母净利润。\n\n';
const mdHeaders=['季度','日期','申万PE','申万40季分位','2.2 PE','2.2 40季分位','申万市值（亿元）','2.2市值（亿元）','申万反推TTM利润（亿元）','2.2 TTM利润（亿元）','2.2公司数'];
const num=v=>Number(v).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
const mdRows=data.map(r=>[r[0],`${r[1].slice(0,4)}-${r[1].slice(4,6)}-${r[1].slice(6,8)}`,num(r[5]),Number(r[6]).toFixed(1)+'%',num(r[11]),Number(r[12]).toFixed(1)+'%',num(r[3]),num(r[9]),num(r[4]),num(r[10]),r[8]]);
await fs.writeFile(`${base}/outputs/bank_pe_10y_quarterly_comparison.md`,intro+[mdHeaders,mdHeaders.map((_,i)=>i<2?'---':'---:'),...mdRows].map(r=>'| '+r.join(' | ')+' |').join('\n')+'\n','utf8');
