import streamlit as st
import pandas as pd
import requests
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# ==============================================================================
# CONFIGURAÇÕES
# ==============================================================================
MARKET_DATA_TOKEN = "dldoN21wYnl4ZzdRejJqQVdfOTNYMVRtaExadERnZ01STGFqTHZQdFNmaz0" 
API_BASE_URL = "https://api.marketdata.app/v1/"
REFRESH_INTERVAL_SECONDS = 300 # 5 minutos

# === TELEGRAM (Suas credenciais inseridas aqui) ===
BOT_TOKEN = "8057186661:AAHM2wEKbaxMr3Tq2ww7hEYWjxvaUzYyX0c"
CHAT_ID = "812707760"

# ==============================================================================
# FUNÇÕES AUXILIARES
# ==============================================================================

def send_telegram_message(message):
    """Envia uma mensagem para o chat configurado no Telegram."""
    # A biblioteca python-telegram-bot precisa ser instalada: pip install python-telegram-bot
    # E também o asyncio, caso não tenha: pip install asyncio
    import asyncio
    import telegram
    
    async def send():
        try:
            bot = telegram.Bot(token=BOT_TOKEN)
            await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='Markdown')
            print(f"Mensagem enviada para o Telegram: {message}")
        except Exception as e:
            print(f"Erro ao enviar mensagem para o Telegram: {e}")
            st.error(f"Falha ao enviar mensagem para o Telegram: {e}")

    try:
        asyncio.run(send())
    except RuntimeError: # Lida com erro de 'event loop is already running' em alguns ambientes
        loop = asyncio.get_running_loop()
        loop.create_task(send())


@st.cache_data(ttl=REFRESH_INTERVAL_SECONDS)
def get_stock_quote(ticker):
    """Busca dados de cotação de uma ação."""
    url = f"{API_BASE_URL}stocks/quotes/{ticker}/?token={MARKET_DATA_TOKEN}"
    try:
        response = requests.get(url, headers={"Accept": "application/json"})
        response.raise_for_status()
        data = response.json()
        if data.get('s') == 'ok':
            return { "last": data.get('last', [None])[0], "open": data.get('open', [None])[0] }
        else:
            return None
    except requests.exceptions.RequestException:
        return None

def render_bar(percentage):
    """Renderiza uma barra de div HTML colorida."""
    if percentage is None: return ""
    width = min(abs(percentage) * 8, 100)
    color = "#1f7a1f" if percentage >= 0 else "#d14040"
    if percentage >= 0:
        bar_html = f'<div style="background-color:{color}; width:{width}%; height:22px; border-radius:3px; margin-left: 50%;"></div>'
    else:
        bar_html = f'<div style="background-color:{color}; width:{width}%; height:22px; border-radius:3px; float: right; margin-right: 50%;"></div>'
    return f'<div style="width:200px; height:22px; background: #f0f2f6; border: 1px solid #ccc; border-radius:3px;">{bar_html}</div>'

# ==============================================================================
# INTERFACE DO STREAMLIT
# ==============================================================================

st.set_page_config(page_title="Dashboard de Trades", layout="wide")
st_autorefresh(interval=REFRESH_INTERVAL_SECONDS * 1000, key="auto_refresher")
st.markdown("## 🦅 Painel de Monitoramento de Operações")

if 'trades' not in st.session_state:
    st.session_state.trades = []

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
                    "ticker": ticker,
                    "put_strike": put_strike,
                    "call_strike": call_strike,
                    "center_price": center_price,
                    "id": f"{ticker}_{put_strike}_{call_strike}_{datetime.now().timestamp()}",
                    "alert_sent": False  # NOVO: Estado de alerta para este trade
                }
                st.session_state.trades.append(new_trade)
                st.success(f"Trade de {ticker} adicionado com centro em ${center_price:.2f}!")
                st.rerun()

# --- Dashboard Principal ---
if not st.session_state.trades:
    st.info("Adicione operações na barra lateral para começar o monitoramento.")
else:
    col_headers = st.columns([1, 1, 1, 1, 1, 2, 1, 0.5])
    headers = ["TICKER", "CHNG", "PUTS", "PRICE", "CALLS", "DIV from center", "%", "DEL"]
    for col, header in zip(col_headers, headers):
        col.markdown(f"**{header}**")
        
    for trade in st.session_state.trades[:]:
        quote = get_stock_quote(trade['ticker'])
        cols = st.columns([1, 1, 1, 1, 1, 2, 1, 0.5])
        
        # LÓGICA DE ALERTA E INDICADOR VISUAL
        ticker_color = "inherit" # Cor padrão
        if quote and quote['last']:
            current_price = quote['last']
            is_breached = (current_price <= trade['put_strike'] or current_price >= trade['call_strike'])
            
            if is_breached:
                ticker_color = "#d14040" # Vermelho se o strike for atingido
                if not trade.get('alert_sent', False): # Verifica se o alerta já foi enviado
                    breached_side = "PUT" if current_price <= trade['put_strike'] else "CALL"
                    message = (
                        f"🚨 *ALERTA DE STRIKE ATINGIDO* 🚨\n\n"
                        f"*Ativo:* `{trade['ticker']}`\n"
                        f"*Preço Atual:* `${current_price:.2f}`\n\n"
                        f"O preço atingiu o strike da *{breached_side}* em `${trade[f'{breached_side.lower()}_strike']:.2f}`."
                    )
                    send_telegram_message(message)
                    trade['alert_sent'] = True # Marca o alerta como enviado
            else:
                # Rearma o alerta se o preço voltar para a zona de segurança
                if trade.get('alert_sent', False):
                    trade['alert_sent'] = False
        
        # Exibição dos dados
        cols[0].markdown(f"**<span style='font-size:1.1em; color:{ticker_color};'>{trade['ticker']}</span>**", unsafe_allow_html=True)
        cols[2].markdown(f"<div style='text-align: right; padding-right: 5px;'>{trade['put_strike']:.2f} &lt;==</div>", unsafe_allow_html=True)
        cols[4].markdown(f"<div style='padding-left: 5px;'>==&gt; {trade['call_strike']:.2f}</div>", unsafe_allow_html=True)

        if quote and quote['last']:
            current_price = quote['last']
            open_price = quote['open']
            
            if open_price:
                chng_percent = ((current_price - open_price) / open_price) * 100
                chng_color = "green" if chng_percent >= 0 else "red"
                cols[1].markdown(f'<span style="color:{chng_color};">{chng_percent:.2f}%</span>', unsafe_allow_html=True)
            else: cols[1].markdown("N/A")

            center_price = trade['center_price']
            div_percent = ((current_price - center_price) / center_price) * 100
            div_color = "green" if div_percent >= 0 else "red"
            
            percent_to_put = ((trade['put_strike'] - current_price) / current_price) * 100
            percent_to_call = ((trade['call_strike'] - current_price) / current_price) * 100
            
            cols[3].markdown(f"**<span style='font-size:1.1em;'>{current_price:.2f}</span>**", unsafe_allow_html=True)
            cols[5].markdown(render_bar(div_percent), unsafe_allow_html=True)
            cols[5].markdown(f'''
                <div style="font-size: 0.8em; display: flex; justify-content: space-between; margin-top: -5px;">
                    <span style="color: #d14040; font-weight: bold;">{percent_to_put:.1f}%</span>
                    <span style="color: #1f7a1f; font-weight: bold;">+{percent_to_call:.1f}%</span>
                </div>
            ''', unsafe_allow_html=True)
            cols[6].markdown(f'<span style="font-weight:bold; color:{div_color};">{div_percent:.0f}%</span>', unsafe_allow_html=True)
        else:
            cols[1].markdown("N/A"); cols[3].markdown("..."); cols[5].markdown(render_bar(0), unsafe_allow_html=True); cols[6].markdown("N/A")
            st.toast(f'Falha ao buscar dados para {trade["ticker"]}', icon="⚠️")

        if cols[7].button("❌", key=f"del_{trade['id']}"):
            st.session_state.trades.remove(trade)
            st.rerun()

        st.markdown('<hr style="margin-top:0.5rem; margin-bottom:0.5rem;">', unsafe_allow_html=True)

    st.caption(f"Última atualização: {datetime.now().strftime('%H:%M:%S')}")
