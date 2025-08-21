import streamlit as st
import pandas as pd
import requests
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import json

# ==============================================================================
# CONFIGURAÇÕES
# ==============================================================================
# As credenciais agora vêm do "Secrets" do Streamlit
MARKET_DATA_TOKEN = st.secrets.get("MARKET_DATA_TOKEN", "")
BOT_TOKEN = st.secrets.get("telegram", {}).get("BOT_TOKEN", "")
CHAT_ID = st.secrets.get("telegram", {}).get("CHAT_ID", "")

API_BASE_URL = "https://api.marketdata.app/v1/"
REFRESH_INTERVAL_SECONDS = 300 # 5 minutos
DB_FILE_PATH = 'trades_data.json' # Nome do nosso "banco de dados" em arquivo

# ==============================================================================
# FUNÇÕES DE PERSISTÊNCIA (Leitura e Escrita no Arquivo JSON)
# ==============================================================================

def load_trades():
    """Carrega a lista de trades do arquivo JSON. Se não existir, retorna uma lista vazia."""
    try:
        with open(DB_FILE_PATH, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_trades(trades_list):
    """Salva a lista atual de trades no arquivo JSON."""
    with open(DB_FILE_PATH, 'w') as f:
        json.dump(trades_list, f, indent=4)

# ==============================================================================
# FUNÇÕES AUXILIARES
# ==============================================================================

def send_telegram_message(message):
    """Envia uma mensagem para o chat configurado no Telegram."""
    import asyncio
    import telegram
    
    async def send():
        try:
            bot = telegram.Bot(token=BOT_TOKEN)
            await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='Markdown')
        except Exception as e:
            st.error(f"Falha ao enviar Telegram: {e}")

    try:
        asyncio.run(send())
    except RuntimeError:
        loop = asyncio.get_running_loop()
        loop.create_task(send())

@st.cache_data(ttl=REFRESH_INTERVAL_SECONDS)
def get_stock_quote(ticker):
    """Busca dados de cotação de uma ação."""
    if not MARKET_DATA_TOKEN: return None
    url = f"{API_BASE_URL}stocks/quotes/{ticker}/?token={MARKET_DATA_TOKEN}"
    try:
        r = requests.get(url, headers={"Accept": "application/json"})
        r.raise_for_status()
        data = r.json()
        return data if data.get('s') == 'ok' else None
    except requests.exceptions.RequestException:
        return None

def render_bar(percentage):
    """Renderiza uma barra de div HTML colorida."""
    if percentage is None: return ""
    width = min(abs(percentage) * 8, 100)
    color = "#1f7a1f" if percentage >= 0 else "#d14040"
    margin, f_right = ("margin-left: 50%;", "") if percentage >= 0 else ("", "float: right; margin-right: 50%;")
    bar_html = f'<div style="background-color:{color}; width:{width}%; height:22px; border-radius:3px; {margin} {f_right}"></div>'
    return f'<div style="width:200px; height:22px; background: #f0f2f6; border: 1px solid #ccc; border-radius:3px;">{bar_html}</div>'

# ==============================================================================
# INICIALIZAÇÃO DO APP
# ==============================================================================

st.set_page_config(page_title="Dashboard de Trades", layout="wide")
st_autorefresh(interval=REFRESH_INTERVAL_SECONDS * 1000, key="auto_refresher")
st.markdown("## 🦅 Painel de Monitoramento de Operações")

# Carrega os trades do arquivo para o session_state, mas apenas uma vez por sessão.
if 'trades' not in st.session_state:
    st.session_state.trades = load_trades()

# --- Barra Lateral para Adicionar Trades ---
with st.sidebar:
    st.header("Adicionar Nova Operação")
    with st.form(key="add_trade_form", clear_on_submit=True):
        ticker = st.text_input("Ticker do Ativo").upper()
        put_strike = st.number_input("Strike da PUT", format="%.2f")
        call_strike = st.number_input("Strike da CALL", format="%.2f")
        submit_button = st.form_submit_button(label="Adicionar Trade")

        if submit_button and ticker:
            if put_strike >= call_strike:
                st.error("O strike da PUT deve ser menor que o strike da CALL.")
            else:
                center_price = (put_strike + call_strike) / 2
                new_trade = {
                    "ticker": ticker, "put_strike": put_strike, "call_strike": call_strike,
                    "center_price": center_price, "id": f"{ticker}_{datetime.now().timestamp()}",
                    "alert_sent": False
                }
                st.session_state.trades.append(new_trade)
                save_trades(st.session_state.trades) # SALVA A LISTA ATUALIZADA
                st.success(f"Trade de {ticker} adicionado!")
                st.rerun()

# --- Dashboard Principal ---
if not st.session_state.trades:
    st.info("Adicione operações na barra lateral para começar.")
else:
    # Cabeçalho da Tabela
    headers = ["TICKER", "CHNG", "PUTS", "PRICE", "CALLS", "DIV from center", "%", "DEL"]
    cols = st.columns([1, 1, 1, 1, 1, 2, 1, 0.5])
    for col, header in zip(cols, headers):
        col.markdown(f"**{header}**")
        
    # Itera sobre os trades para exibição e exclusão
    for i, trade in enumerate(st.session_state.trades):
        quote_data = get_stock_quote(trade['ticker'])
        cols = st.columns([1, 1, 1, 1, 1, 2, 1, 0.5])
        
        # Lógica de Alerta e Cor do Ticker
        ticker_color = "inherit"
        current_price = quote_data.get('last', [None])[0] if quote_data else None

        if current_price:
            is_breached = (current_price <= trade['put_strike'] or current_price >= trade['call_strike'])
            if is_breached:
                ticker_color = "#d14040"
                if not trade.get('alert_sent', False):
                    breached_side = "PUT" if current_price <= trade['put_strike'] else "CALL"
                    message = (f"🚨 *ALERTA DE STRIKE* 🚨\n\n*Ativo:* `{trade['ticker']}`\n*Preço:* `${current_price:.2f}`\n\nAtingiu o strike da *{breached_side}* em `${trade[f'{breached_side.lower()}_strike']:.2f}`.")
                    send_telegram_message(message)
                    st.session_state.trades[i]['alert_sent'] = True
                    save_trades(st.session_state.trades) # Salva o estado do alerta
            elif trade.get('alert_sent', False):
                st.session_state.trades[i]['alert_sent'] = False
                save_trades(st.session_state.trades) # Salva o estado do alerta

        # Exibição dos dados
        cols[0].markdown(f"**<span style='font-size:1.1em; color:{ticker_color};'>{trade['ticker']}</span>**", unsafe_allow_html=True)
        cols[2].markdown(f"<div style='text-align: right; padding-right: 5px;'>{trade['put_strike']:.2f} &lt;==</div>", unsafe_allow_html=True)
        cols[4].markdown(f"<div style='padding-left: 5px;'>==&gt; {trade['call_strike']:.2f}</div>", unsafe_allow_html=True)

        if current_price:
            open_price = quote_data.get('open', [None])[0]
            chng_percent = ((current_price - open_price) / open_price) * 100 if open_price else 0
            chng_color = "green" if chng_percent >= 0 else "red"
            cols[1].markdown(f'<span style="color:{chng_color};">{chng_percent:.2f}%</span>', unsafe_allow_html=True)

            center_price = trade['center_price']
            div_percent = ((current_price - center_price) / center_price) * 100
            div_color = "green" if div_percent >= 0 else "red"
            percent_to_put = ((trade['put_strike'] - current_price) / current_price) * 100
            percent_to_call = ((trade['call_strike'] - current_price) / current_price) * 100

            cols[3].markdown(f"**<span style='font-size:1.1em;'>{current_price:.2f}</span>**", unsafe_allow_html=True)
            cols[5].markdown(render_bar(div_percent), unsafe_allow_html=True)
            cols[5].markdown(f'''<div style="font-size: 0.8em; display: flex; justify-content: space-between; margin-top: -5px;">
                <span style="color: #d14040; font-weight: bold;">{percent_to_put:.1f}%</span>
                <span style="color: #1f7a1f; font-weight: bold;">+{percent_to_call:.1f}%</span></div>''', unsafe_allow_html=True)
            cols[6].markdown(f'<span style="font-weight:bold; color:{div_color};">{div_percent:.0f}%</span>', unsafe_allow_html=True)
        else:
            for c in [1, 3, 5, 6]: cols[c].markdown("...")
            st.toast(f'Falha ao buscar dados para {trade["ticker"]}', icon="⚠️")

        # Botão de Exclusão
        if cols[7].button("❌", key=f"del_{trade['id']}"):
            st.session_state.trades.pop(i) # Remove o trade da lista
            save_trades(st.session_state.trades) # SALVA A LISTA ATUALIZADA
            st.rerun()

        st.markdown('<hr style="margin-top:0.5rem; margin-bottom:0.5rem;">', unsafe_allow_html=True)

    st.caption(f"Última atualização: {datetime.now().strftime('%H:%M:%S')}")
