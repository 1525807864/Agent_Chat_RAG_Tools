<div align="center">

<img src="docs/assets/nexora-logo.svg" alt="Nexora Logo" width="120" />

# Nexora

**澶氭ā寮?AI Agent 骞冲彴 路 瀵硅瘽 路 RAG 路 娴嬭瘯宸ヤ綔鍙?路 娌欑**

[鍔熻兘姒傝](#鍔熻兘姒傝) 路 [蹇€熷紑濮媇(#蹇€熷紑濮嬫湰鍦? 路 [閮ㄧ讲](deploy/README.md) 路 [License](LICENSE)

<br/>

[![GitHub stars](https://img.shields.io/github/stars/1525807864/Agent_Chat_RAG_Tools?style=social)](https://github.com/1525807864/Agent_Chat_RAG_Tools/stargazers)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![React](https://img.shields.io/badge/frontend-React%2018-61dafb)](https://react.dev/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Release](https://img.shields.io/github/v/release/1525807864/Agent_Chat_RAG_Tools?display_name=tag)](https://github.com/1525807864/Agent_Chat_RAG_Tools/releases)

<br/>

**璇█ / Languages**

[涓枃](README.md) 路 [English](README_en.md) 路 [鏃ユ湰瑾瀅(README_ja.md) 路 [頃滉淡鞏碷(docs/i18n/README_ko.md) 路 [Espa帽ol](docs/i18n/README_es.md)

</div>

---

鍩轰簬 LangChain / LangGraph 鐨勫妯″紡 AI Agent 骞冲彴锛氭櫘閫氬璇濄€佹贩鍚堟绱?RAG銆佺粨鏋勫寲鍜ㄨ銆丟raphRAG銆丷eAct 鍗?Agent锛堝惈 MCP锛夈€佸鏅鸿兘浣撳崗浣滐紱鎻愪緵 FastAPI銆乂ite/React 鍓嶇锛圓gentHub 椋庢牸棰嗗煙闂ㄦ埛锛夈€佽嚜鍔ㄦ祴璇曞伐浣滃彴锛屼互鍙婂彲閫?Electron 妗岄潰绔€?

榛樿 LLM 鍏煎 DeepSeek / OpenAI / 鏅鸿氨绛夊崗璁紱鍙€?Cursor Agent SDK 澶勭悊鏀逛唬鐮佺被璇锋眰銆傛椂闂寸粺涓€鎸?**Asia/Shanghai锛堝寳浜椂闂达級** 鍐欏叆涓庡睍绀恒€?

---

## 浜у搧鍏ュ彛

鐧诲綍鍚庨粯璁よ繘鍏?**宸ヤ綔鍙伴棬鎴?*锛坔ash `#/`锛夛細

| 棰嗗煙 | 鐘舵€?| 璇存槑 |
|------|------|------|
| 瀵硅瘽骞冲彴 | 宸蹭笂绾?| `#/chat`锛屽妯″瀷 / RAG / Agent |
| 鑷姩娴嬭瘯骞冲彴 | 宸蹭笂绾?| `#/qa`锛岀敤渚?/ 鎵ц / 鎶ュ憡 / UI Agent |
| 浠ｇ爜璇勫銆佽繍缁淬€佹暟鎹€佺煡璇嗗簱鐙珛鍙扮瓑 | 鍗犱綅 | 鍗＄墖銆屽嵆灏嗗紑鏀俱€嶏紝鍚庣画鎸夊瀭鐩?Agent 鎺ュ叆 |

椤舵爮鍙€屽伐浣滃彴棣栭〉銆嶈繑鍥為棬鎴凤紱瀵硅瘽涓庢祴璇曞彴瑙嗚缁熶竴涓?**澧ㄨ壊 + 棣欐閲?* 椋庢牸銆?

---

## 鍔熻兘姒傝

### 瀵硅瘽妯″紡

| 妯″紡 | 璇存槑 |
|------|------|
| `chat` | 浼氳瘽璁板繂锛圡emory / Solip锛? Skills锛坄/skill`锛? SSE 鐪熸祦寮?|
| `rag` | 绋犲瘑鍚戦噺 + BM25 + RRF 娣峰悎妫€绱紝杞婚噺鏌ヨ璺敱 |
| `consult` | 鍥犲瓙琛ュ叏杩介棶鍚庡啀娣峰悎妫€绱?|
| `graph-rag` | 鍚戦噺妫€绱?+ 鐭ヨ瘑鍥捐氨澧炲己 |
| `agent` | ReAct 宸ュ叿鐜紱宸ヤ綔鍖鸿鍐欙紱閫氱敤 MCP锛涘彲閫変富鍔ㄥ伐鍏峰彂鐜帮紱E2E Playwright |
| `multi` | sequential / debate / router 澶氭櫤鑳戒綋 |

### 骞冲彴鑳藉姏

- **JWT 鐧诲綍涓庣鎴?*銆佺煡璇嗗簱涓婁紶/寤哄簱銆佽璐硅处鏈€丠TTP 闄愭祦涓庡唴瀹硅繃婊? 
- **鑷姩娴嬭瘯宸ヤ綔鍙?*锛氶」鐩€佺敤渚嬨€佽繍琛屻€佹姤鍛婂鍑恒€佹垚鍛樻潈闄愩€侀」鐩煡璇嗗簱锛沀I Agent锛圥laywright锛夋墽琛? 
- **骞冲彴娌欑**锛堝彲閫?Docker锛夛細缁熶竴鎵ц闈紙shell / pwsh / 宸ヤ綔鍖?fs锛夛紝绛栫暐銆佸嚭缃戠櫧鍚嶅崟銆佺┖闂插洖鏀讹紱楂樺嵄鍛戒护鍓嶇瀹℃壒  
- 鐢熶骇 Docker Compose 閮ㄧ讲  

---

## 鏋舵瀯锛圫OLID 鍒嗗眰锛?

```text
鍓嶇闂ㄦ埛 / 瀵硅瘽涓夋爮 / 娴嬭瘯宸ヤ綔鍙?/ Electron
        鈹?
        鈻?
api/锛團astAPI锛氶壌鏉冦€丼SE銆丵A銆乻andbox銆佸弬鏁版牎楠岋級
        鈹?
        鈻?
orchestration/锛圕hatOrchestrator锛欳ursor 璺敱 鈫?mode Capability锛?
        鈹?
        鈻?
application/锛坲se_cases銆乹a銆乻andbox銆丮CP銆乀ools銆丼kills锛?
        鈹?
        鈻?
domain/锛圧equestContext銆丷unResult銆丳orts锛?
        鈹?
        鈻?
infrastructure/锛坮ag銆乤gents銆乵emory銆乻andbox銆乹a filesystem銆丮CP锛?
```

鏍稿績闂ㄩ潰锛歚application/services/agent_application.py`锛堜緷璧栫粍瑁?+ 鍏煎鏃?`ask_*`锛夈€? 
HTTP 瀵硅瘽缁熶竴璧?`app.orchestrator.handle` / `stream`銆? 
鍖椾含鏃堕棿宸ュ叿锛歚shared/timeutil.py`銆佸墠绔?`frontend/src/utils/beijingTime.ts`銆?

---

## 鐩綍缁撴瀯锛堣妭閫夛級

```text
api/                   FastAPI 璺敱锛坈hat / sessions / knowledge / qa / sandbox锛?
application/           鐢ㄤ緥銆乹a锛堝惈 ui_agent / report_export锛夈€乻andbox 鏈嶅姟
orchestration/         ChatOrchestrator + Capability
domain/                棰嗗煙妯″瀷涓?Port
agents/                ReAct / ToolCalling / 澶?Agent 鍥?
rag/                   鍚戦噺銆丅M25銆佹贩鍚堟绱€佸浘璋便€佺粨鏋勫寲鍜ㄨ
memory/                浼氳瘽瀛樺偍涓?MemoryFacade
infrastructure/
  sandbox/             Docker 杩愯鏃躲€佺瓥鐣ャ€佸鎵归闄┿€乺eaper
  qa/                  娴嬭瘯骞冲彴鏂囦欢绯荤粺
frontend/src/
  portal/              棰嗗煙闂ㄦ埛閰嶇疆 domains.ts
  components/HomePortal.tsx
  components/qa/       娴嬭瘯宸ヤ綔鍙伴〉闈?
  components/sandbox/  楂樺嵄鍛戒护瀹℃壒闈㈡澘
  styles/portal.css    闂ㄦ埛 / 鍏ㄥ眬澧ㄩ噾涓婚浠ょ墝瑙?index.css
docker/sandbox/        娌欑闀滃儚 Dockerfile
shared/timeutil.py     鍖椾含鏃堕棿
deploy/                Nginx銆乻ystemd銆佹洿鏂拌剼鏈?
tests/                 pytest
docs/assets/           README 灞曠ず鐢?Logo
docs/i18n/             鍏跺畠璇█绠€鐭鏄?
```

鏇寸粏鐨勪簯閮ㄧ讲璇存槑瑙?[deploy/README.md](deploy/README.md)銆?

---

## 鐜瑕佹眰

- Python 3.11+锛堟帹鑽?3.12/3.13锛?
- Node.js 18+锛堝墠绔?/ Electron锛?
- 鍙€夛細Redis銆丮ySQL 8锛堢敓浜?Compose 鑷甫锛?
- 鍙€夛細Docker锛堝钩鍙版矙绠?`SANDBOX_ENABLED=true`锛?
- 鍙€夛細npx锛圥laywright MCP / E2E / QA UI Agent锛?

---

## 蹇€熷紑濮嬶紙鏈湴锛?

### 1. 鍚庣

```bash
cd LangChain_Demo
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # 鎴?cp .env.example .env
```

缂栬緫 `.env`锛岃嚦灏戦厤缃細

```env
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
MEMORY_BACKEND=sqlite
AUTH_BACKEND=sqlite
AUTH_ENABLED=false
STRICT_PRODUCTION=false
RATE_LIMIT_BACKEND=memory
```

鐭ヨ瘑搴?/ 宓屽叆锛圧AG 闇€瑕侊級锛?

```env
EMBEDDING_API_BASE=https://open.bigmodel.cn/api/paas/v4
EMBEDDING_API_KEY=...
EMBEDDING_MODEL=embedding-3
```

骞冲彴娌欑锛堝彲閫夛紝闇€鏈満 Docker 涓庨暅鍍忥級锛?

```env
SANDBOX_ENABLED=true
SANDBOX_RUNTIME=docker
SANDBOX_IMAGE=nexora-sandbox:latest
SANDBOX_MODE=workspace-write
SANDBOX_NETWORK_MODE=deny
SANDBOX_APPROVAL=on-risky
```

鏋勫缓娌欑闀滃儚绀轰緥锛?

```bash
docker build -t nexora-sandbox:latest -f docker/sandbox/Dockerfile docker/sandbox
```

鍚姩 API锛堝父鐢ㄦ湰鏈虹鍙?**8020**锛屼笌 Electron 榛樿涓€鑷达級锛?

```bash
python -m uvicorn api.server:app --reload --host 127.0.0.1 --port 8020
```

鍋ュ悍妫€鏌ワ細`http://127.0.0.1:8020/health`銆乣/health/ready`  
OpenAPI锛堥潪鐢熶骇涓斿紑鍚椂锛夛細`http://127.0.0.1:8020/docs`

### 2. 鍓嶇

```bash
cd frontend
npm install
# 鍙€夛細frontend/.env
# VITE_API_BASE=http://127.0.0.1:8020
npm run dev
```

娴忚鍣ㄦ墦寮€ Vite 鎻愮ず鐨勫湴鍧€锛堥粯璁?`http://127.0.0.1:5173`锛夈€? 
鐧诲綍鍚庤繘鍏ラ棬鎴凤紱瀵硅瘽 `#/chat`锛屾祴璇曞伐浣滃彴 `#/qa`銆?

### 3. Electron 妗岄潰锛堝彲閫夛級

```bash
cd frontend
npm run dev:desktop
```

鑻ユ湰鏈?API 宸叉墜鍔ㄥ惎鍔紝鍙敤 `npm run dev:desktop:no-api`銆? 
鎵撳寘 Windows 瀹夎鍖咃細`npm run dist`銆?

### 4. CLI

```bash
python main.py
```

---

## 瀵硅瘽 API 绀轰緥

```bash
curl -s http://127.0.0.1:8020/api/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"message\":\"浣犲ソ\",\"mode\":\"chat\",\"session_id\":\"demo\"}"
```

寮€鍚壌鏉冨悗闇€甯?`Authorization: Bearer <token>`锛堝厛璋冪櫥褰曟帴鍙ｏ級銆? 
娴佸紡锛歚POST /api/chat/stream`锛圫SE锛夈€?

鏀寔鐨?`mode`锛歚chat` | `rag` | `consult` | `graph-rag` | `agent` | `multi`銆?

鍏跺畠涓昏鍓嶇紑锛?

| 鍓嶇紑 | 璇存槑 |
|------|------|
| `/api/qa/*` | 娴嬭瘯宸ヤ綔鍙伴」鐩?/ 鐢ㄤ緥 / 杩愯 / 鎶ュ憡 |
| `/api/sandbox/*` | 娌欑浼氳瘽涓庢墽琛岋紙闇€鍚敤閰嶇疆锛?|
| `/api/knowledge/*` | 鐭ヨ瘑搴撴枃妗ｄ笌寤哄簱 |

---

## 閰嶇疆瑕佺偣

| 鍙橀噺 | 鍚箟 |
|------|------|
| `DEEPSEEK_API_KEY` / `DEEPSEEK_API_BASE` | 榛樿鑱婂ぉ妯″瀷锛圤penAI 鍏煎锛?|
| `CURSOR_API_KEY` | 鏈夊瘑閽ユ椂锛宎gent / 鏀逛唬鐮佺被 chat 鍙蛋 Cursor |
| `MEMORY_BACKEND` | `sqlite`锛堟湰鍦帮級鎴?`redis` |
| `AUTH_ENABLED` / `AUTH_BACKEND` | 閴存潈寮€鍏筹紱`sqlite` 鎴?`mysql` |
| `MCP_SERVERS_JSON` | 閫氱敤 MCP 鏈嶅姟鍣?JSON 鏁扮粍锛涚┖鍒欎笉鎷夊閮?MCP |
| `ACTIVE_TOOL_DISCOVERY` | Agent 涓诲姩鍙戠幇宸ュ叿锛堝伐鍏峰鏃跺啀寮€锛?|
| `HYBRID_*` | 娣峰悎妫€绱笌璺敱鍣?|
| `TAVILY_API_KEY` | `web_search` 宸ュ叿 |
| `SANDBOX_ENABLED` 绛?| 骞冲彴娌欑锛堣 `.env.example`锛?|

瀹屾暣妯℃澘锛歚.env.example`銆佺敓浜э細`.env.production.example`銆?

鍓嶇妯″瀷璁剧疆淇濆瓨鍦ㄦ湰鏈烘祻瑙堝櫒锛汯ey 鐣欑┖鏃跺悗绔敤鏈嶅姟绔?`.env` 鍏滃簳銆傚垏鎹㈠巶鍟嗘椂璇峰悓鏃舵敼 **API Key + API Base + Model Name**銆?

---

## 娴嬭瘯

```bash
python -m pytest tests/test_orchestration_smoke.py tests/test_orchestrator_matrix.py tests/test_orchestrator_stream.py tests/test_layering.py tests/test_use_cases_unit.py tests/test_tool_gateway.py tests/test_routing_policy.py tests/test_facade_helpers.py tests/test_chat_astream.py tests/test_qa_backend.py -q
```

鍒嗗眰绾﹀畾锛歚domain/`銆乣api/` 涓嶅緱鐩存帴 `import langchain`锛堢敱娴嬭瘯闂搁棬妫€鏌ワ級銆?

寤鸿鎵嬪伐鍐掔儫锛氶棬鎴疯繘鍏ュ璇?/ 娴嬭瘯鍙?鈫?鍚?mode 鍙戜竴杞?鈫?QA 寤洪」鐩窇鐢ㄤ緥 鈫掞紙鍙€夛級娌欑楂樺嵄鍛戒护瀹℃壒銆?

DeepEval 璇勬祴锛堝彲閫夛紝闇€鍙﹁寮€鍙戜緷璧栵級锛氳 `tests/power_test/`銆?

---

## 鐢熶骇閮ㄧ讲锛堟憳瑕侊級

鎺ㄨ崘 Docker Compose锛堝惈 Redis銆丮ySQL銆丄PI銆丯ginx锛夛細

```bash
cp .env.production.example .env   # 濉啓瀵嗛挜涓庣鐞嗗憳瀵嗙爜
docker compose up -d --build
```

- 瀹夊叏缁勫彧寮€ 80/443锛屼笉瑕佹毚闇?8020 / 6379 / 3306  
- 鐢熶骇锛歚AUTH_ENABLED=true`銆乣STRICT_PRODUCTION=true`銆乣OPENAPI_ENABLED=false`  
- 璇︽儏涓?GitHub Actions 鑷姩閮ㄧ讲锛歔deploy/README.md](deploy/README.md)

---

## 鎶€鏈爤

- **鍚庣**锛欶astAPI銆丩angChain銆丩angGraph銆丆hroma銆丅M25銆丯etworkX銆丷edis/SQLite/MySQL銆丏ocker 娌欑  
- **鍓嶇**锛歊eact 18銆乂ite銆乀ypeScript銆丄nt Design銆丒lectron锛堝彲閫夛級  
- **宸ュ叿**锛歍avily 鎼滅储銆丮CP锛堝惈 Playwright E2E / QA UI锛夈€丆ursor SDK锛堝彲閫夛級

---

## 澶氳瑷€鏂囨。

| 璇█ | 鏂囦欢 |
|------|------|
| 涓枃锛堜富鏂囨。锛?| [README.md](README.md) |
| English | [README_en.md](README_en.md) |
| 鏃ユ湰瑾?| [README_ja.md](README_ja.md) |
| 頃滉淡鞏?| [docs/i18n/README_ko.md](docs/i18n/README_ko.md) |
| Espa帽ol | [docs/i18n/README_es.md](docs/i18n/README_es.md) |

瀹屾暣缁嗚妭浠ヤ腑鏂囦富鏂囨。涓哄噯锛涘叾瀹冭瑷€涓哄璇讳笌蹇€熷紑濮嬫憳瑕併€?

---

## License

[MIT](LICENSE)
