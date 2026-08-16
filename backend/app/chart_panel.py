CANDLE_CHART_SCRIPT = r'''
<style>
.trade-chart-card{margin-top:8px;padding:10px 12px}.trade-chart-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px}.trade-chart-title{font-weight:900;font-size:16px}.trade-chart-meta{font-size:11px;color:var(--mut)}.trade-chart-tools{display:flex;gap:6px;align-items:center}.trade-chart-tools select{background:#0a141e;color:#eef5fb;border:1px solid var(--line);border-radius:8px;padding:6px 8px}.chart-wrap{position:relative;height:360px;background:#07111a;border:1px solid var(--line);border-radius:10px;overflow:hidden}.chart-wrap canvas{width:100%;height:100%;display:block}.chart-legend{display:flex;gap:12px;flex-wrap:wrap;font-size:11px;margin-top:7px}.lg{display:inline-flex;align-items:center;gap:5px}.dot{width:9px;height:9px;border-radius:50%}.entry-dot{background:#2f9bff}.tp-dot{background:#43d78f}.sl-dot{background:#ff5d6c}.price-dot{background:#f0c94d}
@media(max-width:800px){.chart-wrap{height:300px}.trade-chart-head{align-items:flex-start;flex-direction:column}}
</style>
<script>
(function(){
  let candles=[], botState=null, selectedSymbol='BTCUSDT', interval='1m';
  const fmt=n=>Number(n||0).toLocaleString('ru-RU',{maximumFractionDigits:6});
  function install(){
    if(document.getElementById('tradeChartCard'))return;
    const perf=document.getElementById('performancePanel');
    const host=perf?.parentElement || document.querySelector('.wrap');
    if(!host)return;
    const card=document.createElement('div');
    card.id='tradeChartCard'; card.className='card trade-chart-card';
    card.innerHTML=`<div class="trade-chart-head"><div><div class="trade-chart-title">ГРАФИК СДЕЛКИ / LIVE CANDLES</div><div id="tradeChartMeta" class="trade-chart-meta">Загрузка...</div></div><div class="trade-chart-tools"><select id="chartTf"><option value="1m">1m</option><option value="3m">3m</option><option value="5m">5m</option><option value="15m">15m</option></select><button class="btn stop" id="chartRefresh" style="padding:7px 10px">↻</button></div></div><div class="chart-wrap"><canvas id="tradeCanvas"></canvas></div><div class="chart-legend"><span class="lg"><i class="dot entry-dot"></i>ENTRY</span><span class="lg"><i class="dot tp-dot"></i>TAKE PROFIT</span><span class="lg"><i class="dot sl-dot"></i>STOP LOSS</span><span class="lg"><i class="dot price-dot"></i>ТЕКУЩАЯ ЦЕНА</span></div>`;
    if(perf)host.insertBefore(card,perf);else host.appendChild(card);
    document.getElementById('chartTf').addEventListener('change',e=>{interval=e.target.value;loadChart()});
    document.getElementById('chartRefresh').addEventListener('click',loadChart);
    window.addEventListener('resize',draw);
  }
  function activeTrade(){
    const rt=botState?.runtime||{};
    const p=(botState?.positions||[])[0];
    const t=rt.last_trade||{};
    if(p){
      return {symbol:p.symbol||t.symbol,entry:Number(p.entry_price||t.entry_price||0),mark:Number(p.mark_price||0),tp:Number(t.take_profit||0),sl:Number(t.stop_loss||0),side:Number(p.position_amt||0)>0?'LONG':'SHORT',open:true};
    }
    if(t?.symbol){return {symbol:t.symbol,entry:Number(t.entry_price||0),mark:0,tp:Number(t.take_profit||0),sl:Number(t.stop_loss||0),side:t.side==='BUY'?'LONG':'SHORT',open:false};}
    return null;
  }
  async function loadChart(){
    install();
    try{
      const s=await fetch('/bot/status',{cache:'no-store'}).then(r=>r.json()); botState=s;
      const tr=activeTrade();
      const selector=document.querySelector('select#symbol') || document.querySelector('select');
      selectedSymbol=(tr?.symbol || selector?.value || selectedSymbol || 'BTCUSDT').toUpperCase();
      const r=await fetch(`/market/klines?symbol=${encodeURIComponent(selectedSymbol)}&interval=${encodeURIComponent(interval)}&limit=120`,{cache:'no-store'});
      if(!r.ok)throw new Error(await r.text()); candles=await r.json();
      const meta=document.getElementById('tradeChartMeta');
      if(meta){meta.textContent=tr?`${selectedSymbol} • ${interval} • ${tr.side} • Entry ${fmt(tr.entry)} • TP ${fmt(tr.tp)} • SL ${fmt(tr.sl)}`:`${selectedSymbol} • ${interval} • нет открытой позиции`;}
      draw();
    }catch(e){const meta=document.getElementById('tradeChartMeta');if(meta)meta.textContent='Ошибка графика: '+e.message;}
  }
  function drawLine(ctx,y,text,color,w){ctx.save();ctx.strokeStyle=color;ctx.lineWidth=1.3;ctx.setLineDash([6,4]);ctx.beginPath();ctx.moveTo(48,y);ctx.lineTo(w-8,y);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle=color;ctx.font='11px sans-serif';ctx.fillText(text,52,Math.max(12,y-4));ctx.restore();}
  function draw(){
    const canvas=document.getElementById('tradeCanvas');if(!canvas||!candles.length)return;
    const dpr=window.devicePixelRatio||1,w=canvas.clientWidth,h=canvas.clientHeight;canvas.width=Math.floor(w*dpr);canvas.height=Math.floor(h*dpr);const ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
    const tr=activeTrade();
    let min=Math.min(...candles.map(c=>c.low)),max=Math.max(...candles.map(c=>c.high));
    [tr?.entry,tr?.tp,tr?.sl,tr?.mark].forEach(v=>{if(v>0){min=Math.min(min,v);max=Math.max(max,v)}});const pad=(max-min)*0.08||1;min-=pad;max+=pad;
    const top=12,bottom=h-26,left=48,right=w-8,plotH=bottom-top,plotW=right-left;const y=v=>top+(max-v)/(max-min)*plotH;
    ctx.strokeStyle='#142433';ctx.lineWidth=1;ctx.font='10px sans-serif';ctx.fillStyle='#7890a4';for(let i=0;i<=5;i++){const yy=top+i*plotH/5;ctx.beginPath();ctx.moveTo(left,yy);ctx.lineTo(right,yy);ctx.stroke();const price=max-(max-min)*i/5;ctx.fillText(fmt(price),3,yy+3)}
    const step=plotW/candles.length,body=Math.max(2,step*0.58);candles.forEach((c,i)=>{const x=left+i*step+step/2,up=c.close>=c.open,col=up?'#43d78f':'#ff5d6c';ctx.strokeStyle=col;ctx.fillStyle=col;ctx.beginPath();ctx.moveTo(x,y(c.high));ctx.lineTo(x,y(c.low));ctx.stroke();const yo=y(Math.max(c.open,c.close)),yc=y(Math.min(c.open,c.close));ctx.fillRect(x-body/2,yo,body,Math.max(1,yc-yo));});
    if(tr){if(tr.entry>0)drawLine(ctx,y(tr.entry),`ENTRY ${fmt(tr.entry)}`,'#2f9bff',w);if(tr.tp>0)drawLine(ctx,y(tr.tp),`TP +$1 target ${fmt(tr.tp)}`,'#43d78f',w);if(tr.sl>0)drawLine(ctx,y(tr.sl),`SL ${fmt(tr.sl)}`,'#ff5d6c',w);if(tr.mark>0)drawLine(ctx,y(tr.mark),`MARK ${fmt(tr.mark)}`,'#f0c94d',w);}
  }
  function init(){install();loadChart();setInterval(loadChart,5000)}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
</script>
'''
