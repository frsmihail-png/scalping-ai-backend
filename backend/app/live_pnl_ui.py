LIVE_PNL_SCRIPT = r'''
<style>
.livepnl{grid-column:span 12!important;padding:10px 12px!important}
.livepnl-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px}
.livepnl-title{font-size:15px;font-weight:900}.livepnl-state{font-size:11px;font-weight:900;padding:5px 8px;border-radius:999px;border:1px solid var(--line)}
.livepnl-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:7px}
.livepnl-box{background:#09131c;border:1px solid var(--line);border-radius:9px;padding:8px 10px;min-width:0}
.livepnl-label{font-size:10px;color:var(--mut);text-transform:uppercase}.livepnl-value{font-size:19px;font-weight:900;margin-top:3px;white-space:nowrap}
.livepnl-track{height:8px;border-radius:999px;background:#182735;overflow:hidden;margin-top:9px}.livepnl-fill{height:100%;width:0;background:var(--green);transition:width .25s}
.livepnl-note{font-size:10px;color:var(--mut);margin-top:6px}
@media(max-width:1000px){.livepnl-grid{grid-template-columns:repeat(3,1fr)}}
@media(max-width:600px){.livepnl-grid{grid-template-columns:1fr 1fr}.livepnl-value{font-size:16px}}
</style>
<script>
(function(){
  const fmt=(n,d=2)=>Number(n||0).toLocaleString('ru-RU',{minimumFractionDigits:d,maximumFractionDigits:d});
  const color=(v)=>Number(v)>0?'green':Number(v)<0?'red':'amber';
  function install(){
    if(document.getElementById('livePnlCard')) return;
    const tbody=document.getElementById('positions');
    const posCard=tbody?.closest('.card');
    if(!posCard || !posCard.parentElement) return;
    const card=document.createElement('div');
    card.id='livePnlCard'; card.className='card livepnl';
    card.innerHTML=`
      <div class="livepnl-head"><div><div class="livepnl-title">LIVE PNL / ЧИСТАЯ ПРИБЫЛЬ ПО ОТКРЫТОЙ СДЕЛКЕ</div><div class="livepnl-note">PnL Binance минус расчётные комиссии и резерв на проскальзывание</div></div><span id="lpState" class="livepnl-state amber">НЕТ ПОЗИЦИИ</span></div>
      <div class="livepnl-grid">
        <div class="livepnl-box"><div class="livepnl-label">Gross PnL Binance</div><div id="lpGross" class="livepnl-value">—</div></div>
        <div class="livepnl-box"><div class="livepnl-label">Расчётные расходы</div><div id="lpCosts" class="livepnl-value amber">—</div></div>
        <div class="livepnl-box"><div class="livepnl-label">Net PnL сейчас</div><div id="lpNet" class="livepnl-value">—</div></div>
        <div class="livepnl-box"><div class="livepnl-label">Цель чистыми</div><div id="lpTarget" class="livepnl-value green">+1,00 USDT</div></div>
        <div class="livepnl-box"><div class="livepnl-label">Буфер TP</div><div id="lpBuffer" class="livepnl-value">+0,25 USDT</div></div>
        <div class="livepnl-box"><div class="livepnl-label">До расчётного TP</div><div id="lpRemain" class="livepnl-value">—</div></div>
      </div>
      <div class="livepnl-track"><div id="lpFill" class="livepnl-fill"></div></div>
      <div id="lpNote" class="livepnl-note">Ожидание открытой позиции…</div>`;
    posCard.parentElement.insertBefore(card,posCard);
  }
  function setVal(id,text,cls){const e=document.getElementById(id);if(!e)return;e.textContent=text;if(cls)e.className='livepnl-value '+cls}
  async function refresh(){
    install();
    try{
      const r=await fetch('/bot/status',{cache:'no-store'}); if(!r.ok) throw new Error(await r.text());
      const d=await r.json();
      const p=(d.positions||[])[0];
      const trade=d.runtime?.last_trade||{};
      const target=Number(d.target_net_profit_usdt ?? trade.target_net_profit_usdt ?? 1);
      const buffer=Number(d.profit_safety_buffer_usdt ?? trade.profit_safety_buffer_usdt ?? .25);
      const state=document.getElementById('lpState'), note=document.getElementById('lpNote'), fill=document.getElementById('lpFill');
      setVal('lpTarget','+'+fmt(target,2)+' USDT','green'); setVal('lpBuffer','+'+fmt(buffer,2)+' USDT','amber');
      if(!p){
        if(state){state.textContent='НЕТ ПОЗИЦИИ';state.className='livepnl-state amber'}
        ['lpGross','lpCosts','lpNet','lpRemain'].forEach(id=>setVal(id,'—','amber')); if(fill)fill.style.width='0%';
        if(note)note.textContent='Когда бот откроет позицию, здесь появится чистый PnL в реальном времени.'; return;
      }
      const gross=Number(p.unrealized_profit||0);
      const entry=Number(p.entry_price||0), mark=Number(p.mark_price||0), qty=Math.abs(Number(p.position_amt||0));
      const entryNotional=entry*qty, markNotional=mark*qty;
      const feeRate=Number(d.taker_fee_rate_assumed ?? .0005), slip=Number(d.roundtrip_slippage_rate_assumed ?? .0004);
      // Binance unrealized PnL excludes commissions. Estimate both entry+exit taker fees plus a round-trip slippage reserve.
      const fees=entryNotional*feeRate + markNotional*feeRate;
      const slipReserve=entryNotional*slip;
      const costs=fees+slipReserve;
      const net=gross-costs;
      const tpNet=target+buffer;
      const remain=Math.max(0,tpNet-net);
      setVal('lpGross',(gross>=0?'+':'')+fmt(gross,2)+' USDT',color(gross));
      setVal('lpCosts','−'+fmt(costs,2)+' USDT','amber');
      setVal('lpNet',(net>=0?'+':'')+fmt(net,2)+' USDT',color(net));
      setVal('lpRemain',remain<=0?'ГОТОВО': '+'+fmt(remain,2)+' USDT',remain<=0?'green':'amber');
      const pct=Math.max(0,Math.min(100,(net/tpNet)*100)); if(fill)fill.style.width=pct+'%';
      if(state){
        if(net>=tpNet){state.textContent='TP READY';state.className='livepnl-state green'}
        else if(net>=target){state.textContent='ЦЕЛЬ $1 ДОСТИГНУТА';state.className='livepnl-state green'}
        else if(net>0){state.textContent='В ПЛЮСЕ';state.className='livepnl-state green'}
        else{state.textContent='ЖДЁМ TP';state.className='livepnl-state amber'}
      }
      if(note)note.textContent=`${p.symbol} • Entry ${fmt(entry,4)} • Mark ${fmt(mark,4)} • расходы являются оценкой; фактическая комиссия Binance может немного отличаться.`;
    }catch(e){const n=document.getElementById('lpNote');if(n)n.textContent='Ошибка LIVE PnL: '+e.message}
  }
  window.refreshLivePnl=refresh;
  function init(){install();refresh();setInterval(refresh,2000)}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
</script>
'''
