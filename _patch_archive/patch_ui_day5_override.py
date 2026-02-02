import shutil
from datetime import datetime
from pathlib import Path

INDEX = Path(r"C:\autobot\app\templates\index.html")

SCRIPT = r"""
<script id="day5_override">
(function(){
  const S = window.__day5 = window.__day5 || { requiredOnly:true, allParams:null, strategyId:null };

  function norm(rows){
    if(Array.isArray(rows)) return rows;
    if(rows && Array.isArray(rows.items)) return rows.items;
    return [];
  }

  async function fetchTemplates(strategyId, configId){
    const t1 = await fetch(`/api/strategies/${strategyId}/templates/tradingview?config_id=${configId}&include_hash=true`).then(r=>r.json());
    const t0 = await fetch(`/api/strategies/${strategyId}/templates/tradingview?config_id=${configId}&include_hash=false`).then(r=>r.json());
    return {with_hash:t1, without_hash:t0};
  }

  function ensurePanels(strategyId, allCount, shownCount){
    const body = document.getElementById('modal-body');
    if(!body) return;

    // tools(토글/카운트) 박스
    let tools = document.getElementById('cfg-tools');
    if(!tools){
      tools = document.createElement('div');
      tools.id='cfg-tools';
      tools.style.cssText='padding:10px 12px;margin-bottom:10px;border:1px solid #eee;border-radius:10px;background:#fafafa;display:flex;gap:12px;align-items:center;flex-wrap:wrap;';
      tools.innerHTML = `
        <label style="display:inline-flex;align-items:center;gap:8px;">
          <input type="checkbox" id="cfg_required_only" checked />
          <span>필수만 보기(99.*)</span>
        </label>
        <span id="cfg_counts" style="opacity:.8"></span>
        <span style="opacity:.6">※ 0개면 sync 필요</span>
      `;
      body.prepend(tools);

      tools.querySelector('#cfg_required_only').addEventListener('change', ()=>{
        S.requiredOnly = tools.querySelector('#cfg_required_only').checked;
        if(typeof window.renderStrategyConfigModal==='function'){
          window.renderStrategyConfigModal(S.strategyId, S.allParams);
        }
      });
    }

    tools.querySelector('#cfg_required_only').checked = (S.requiredOnly !== false);
    tools.querySelector('#cfg_counts').textContent = `파라미터: ${shownCount}/${allCount}`;

    // 저장결과/템플릿 패널
    let res = document.getElementById('cfg-save-result');
    if(!res){
      res=document.createElement('div');
      res.id='cfg-save-result';
      res.style.cssText='margin-top:12px;padding:10px 12px;border:1px solid #eee;border-radius:10px;background:#fff;';
      res.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;">
          <b>저장 결과</b>
          <button type="button" id="cfg_copy_result" class="secondary">복사</button>
        </div>
        <pre id="cfg_result_pre" class="code" style="white-space:pre-wrap;margin:8px 0 0;">(아직 저장 전)</pre>

        <div style="height:10px"></div>

        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;">
          <b>TradingView 템플릿 (hash 포함)</b>
          <button type="button" id="cfg_copy_tpl1" class="secondary">복사</button>
        </div>
        <pre id="cfg_tpl1_pre" class="code" style="white-space:pre-wrap;margin:8px 0 0;">(저장 후 자동 출력)</pre>

        <div style="height:10px"></div>

        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;">
          <b>TradingView 템플릿 (hash 미포함)</b>
          <button type="button" id="cfg_copy_tpl0" class="secondary">복사</button>
        </div>
        <pre id="cfg_tpl0_pre" class="code" style="white-space:pre-wrap;margin:8px 0 0;">(저장 후 자동 출력)</pre>
      `;
      body.appendChild(res);

      const copy = async(preId)=>{
        const el=document.getElementById(preId);
        if(!el) return;
        const txt=el.textContent||'';
        try{ await navigator.clipboard.writeText(txt); }
        catch(e){ prompt("복사:", txt); }
      };
      res.querySelector('#cfg_copy_result').addEventListener('click', ()=>copy('cfg_result_pre'));
      res.querySelector('#cfg_copy_tpl1').addEventListener('click', ()=>copy('cfg_tpl1_pre'));
      res.querySelector('#cfg_copy_tpl0').addEventListener('click', ()=>copy('cfg_tpl0_pre'));
    }
  }

  function showSyncNeeded(strategyId){
    const body=document.getElementById('modal-body');
    const footer=document.getElementById('modal-footer');
    if(body){
      body.innerHTML = `
        <div class="err">이 전략은 signal_params가 0개입니다. 먼저 <b>signal-params:sync</b>가 필요합니다.</div>
        <div class="hint" style="margin-top:10px;">
          <pre class="code">curl.exe -sS -X POST "http://127.0.0.1:8000/api/strategies/${strategyId}/signal-params:sync" -H "Content-Type: application/json; charset=utf-8" --data-binary "@sync_payload.json"</pre>
        </div>
      `;
    }
    if(footer){
      footer.innerHTML = `<button class="secondary" onclick="closeModal && closeModal()">닫기</button>`;
    }
  }

  // 1) openStrategyConfig 오버라이드: params 0이면 안내, 아니면 render로 강제
  if(typeof window.openStrategyConfig === 'function'){
    const orig = window.openStrategyConfig;
    window.openStrategyConfig = async function(strategyId){
      S.strategyId = strategyId;
      try{
        const params = (typeof window.api==='function')
          ? await window.api(`/api/strategies/${strategyId}/signal-params`)
          : await fetch(`/api/strategies/${strategyId}/signal-params`).then(r=>r.json());

        S.allParams = params;

        const arr = norm(params);
        if(arr.length===0){
          try{ await orig.call(this, strategyId); }catch(e){}
          showSyncNeeded(strategyId);
          return;
        }

        if(typeof window.renderStrategyConfigModal==='function'){
          window.renderStrategyConfigModal(strategyId, params);
          return;
        }

        return orig.call(this, strategyId);
      }catch(e){
        return orig.call(this, strategyId);
      }
    };
  }

  // 2) renderStrategyConfigModal 오버라이드: 99.* 필수만 보기 + 패널 주입
  if(typeof window.renderStrategyConfigModal === 'function'){
    const origR = window.renderStrategyConfigModal;
    window.renderStrategyConfigModal = function(strategyId, rows){
      S.strategyId = strategyId;
      S.allParams = rows;

      const allArr = norm(rows);
      const shownArr = (S.requiredOnly !== false)
        ? allArr.filter(p => String(p.group_name||'').startsWith('99'))
        : allArr;

      const ret = origR.call(this, strategyId, shownArr);
      try{ ensurePanels(strategyId, allArr.length, shownArr.length); }catch(e){}
      return ret;
    };
  }

  // 3) api 오버라이드: config 저장 성공 시 결과 + 템플릿 2종 자동 출력
  if(typeof window.api === 'function'){
    const origApi = window.api;
    window.api = async function(path, opts){
      const res = await origApi.call(this, path, opts);

      try{
        const isSave =
          typeof path === 'string' &&
          /\/api\/strategies\/\d+\/configs$/.test(path) &&
          opts &&
          String(opts.method||'GET').toUpperCase()==='POST';

        if(isSave && res && res.ok && res.config_id){
          const pre = document.getElementById('cfg_result_pre');
          if(pre) pre.textContent = JSON.stringify(res, null, 2);

          const tpls = await fetchTemplates(S.strategyId, res.config_id);

          const pre1 = document.getElementById('cfg_tpl1_pre');
          const pre0 = document.getElementById('cfg_tpl0_pre');

          if(pre1) pre1.textContent = JSON.stringify(tpls.with_hash, null, 2);
          if(pre0) pre0.textContent = JSON.stringify(tpls.without_hash, null, 2);
        }
      }catch(e){}

      return res;
    };
  }
})();
</script>
"""

def backup(p: Path):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    b = p.with_suffix(p.suffix + f".bak_{ts}")
    shutil.copy2(p, b)
    return b

def main():
    if not INDEX.exists():
        raise SystemExit(f"index.html not found: {INDEX}")

    src = INDEX.read_text(encoding="utf-8", errors="replace")

    if 'id="day5_override"' in src:
        print("Skip: day5_override already injected")
        return

    if "</body>" not in src:
        raise SystemExit("ERROR: </body> not found in index.html")

    b = backup(INDEX)
    print("Backup:", b)

    src2 = src.replace("</body>", SCRIPT + "\n</body>", 1)
    INDEX.write_text(src2, encoding="utf-8")
    print("Injected day5_override into:", INDEX)

if __name__ == "__main__":
    main()
