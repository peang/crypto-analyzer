import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time

# Telegram Bot Configuration
CHAT_ID = ''
TELEGRAM_API_URL = "https://api.telegram.org/bot/"
COINGECKO_API_URL = "https://api.coingecko.com/api/v3/coins/"

# List of coins (include Bitcoin and Ethereum)
COINS = [
    "bitcoin", "ethereum", "solana", "cardano", "polkadot", "litecoin", "binancecoin"
]

# Helper functions
def fetch_data(symbol):
    try:
        url = f"{COINGECKO_API_URL}{symbol}/market_chart?vs_currency=usd&days=7"
        response = requests.get(url)
        response.raise_for_status()  # Ensure the request was successful
        data = response.json()
        if 'prices' not in data:
            raise ValueError(f"Key 'prices' not found in response for {symbol}")
        prices = data['prices']
        return pd.DataFrame(prices, columns=['timestamp', 'price'])
    except ValueError as e:
        print(e)
        return pd.DataFrame()  # Return empty DataFrame if key not found
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data for {symbol}: {e}")
        return pd.DataFrame()  # Return empty DataFrame in case of request error

def calculate_indicators(df):
    if df.empty:
        return df  # Return empty DataFrame if no data is available
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    df['SMA_20'] = df['price'].rolling(window=20).mean()
    df['EMA_20'] = df['price'].ewm(span=20, adjust=False).mean()
    df['EMA_50'] = df['price'].ewm(span=50, adjust=False).mean()
    df['MACD'] = df['EMA_20'] - df['EMA_50']
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['Bollinger_Middle'] = df['price'].rolling(window=20).mean()
    df['Bollinger_Upper'] = df['Bollinger_Middle'] + (df['price'].rolling(window=20).std() * 2)
    df['Bollinger_Lower'] = df['Bollinger_Middle'] - (df['price'].rolling(window=20).std() * 2)
    df['RSI'] = calculate_rsi(df['price'])
    return df

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def send_telegram_message(message):
    try:
        response = requests.get(f"{TELEGRAM_API_URL}sendMessage", params={"chat_id": CHAT_ID, "text": message})
        response.raise_for_status()  # Raise an error for bad HTTP status codes
    except requests.exceptions.RequestException as e:
        print(f"Error sending message: {e}")

def analyze_data(df, symbol):
    if df.empty:
        return  # Skip analysis if DataFrame is empty

    latest = df.iloc[-1]
    future_prices_up_8h = df['price'].rolling(window=48).apply(lambda x: x.iloc[-1] * 1.10)  # 10% increase over 8 hours
    future_prices_down_8h = df['price'].rolling(window=48).apply(lambda x: x.iloc[-1] * 0.90)  # 10% decrease over 8 hours
    projected_price_up_8h = future_prices_up_8h.iloc[-1]
    projected_price_down_8h = future_prices_down_8h.iloc[-1]

    future_prices_up_7d = df['price'].rolling(window=336).apply(lambda x: x.iloc[-1] * 1.10)  # 10% increase over 7 days
    future_prices_down_7d = df['price'].rolling(window=336).apply(lambda x: x.iloc[-1] * 0.90)  # 10% decrease over 7 days
    projected_price_up_7d = future_prices_up_7d.iloc[-1]
    projected_price_down_7d = future_prices_down_7d.iloc[-1]

    message_8h = ""
    message_7d = ""

    # Calculate percentage change for 8 hours
    if projected_price_up_8h > latest['price']:
        profit_percentage_8h = ((projected_price_up_8h - latest['price']) / latest['price']) * 100
        message_8h = (f"Buy {symbol.capitalize()} now! The current price is ${latest['price']:.2f}. "
                      f"The projected price could increase to around ${projected_price_up_8h:.2f} over the next 8 hours. "
                      f"This represents an estimated profit of {profit_percentage_8h:.2f}%. "
                      f"You can consider selling this coin after 8 hours to potentially realize this profit.")
    elif projected_price_down_8h < latest['price']:
        loss_percentage_8h = ((latest['price'] - projected_price_down_8h) / latest['price']) * 100
        message_8h = (f"Sell {symbol.capitalize()} now! The current price is ${latest['price']:.2f}. "
                      f"The indicators suggest that the price might decrease to around ${projected_price_down_8h:.2f} over the next 8 hours. "
                      f"This represents a potential loss of {loss_percentage_8h:.2f}%. "
                      f"You might want to cut losses or take profits if the price starts to drop further.")

    # Calculate percentage change for 7 days
    if projected_price_up_7d > latest['price']:
        profit_percentage_7d = ((projected_price_up_7d - latest['price']) / latest['price']) * 100
        message_7d = (f"Buy {symbol.capitalize()} now! The current price is ${latest['price']:.2f}. "
                      f"The projected price could increase to around ${projected_price_up_7d:.2f} over the next 7 days. "
                      f"This represents an estimated profit of {profit_percentage_7d:.2f}%. "
                      f"You can consider selling this coin after 7 days to potentially realize this profit.")
    elif projected_price_down_7d < latest['price']:
        loss_percentage_7d = ((latest['price'] - projected_price_down_7d) / latest['price']) * 100
        message_7d = (f"Sell {symbol.capitalize()} now! The current price is ${latest['price']:.2f}. "
                      f"The indicators suggest that the price might decrease to around ${projected_price_down_7d:.2f} over the next 7 days. "
                      f"This represents a potential loss of {loss_percentage_7d:.2f}%. "
                      f"You might want to cut losses or take profits if the price starts to drop further.")

    if message_8h:
        send_telegram_message(message_8h)
    if message_7d:
        send_telegram_message(message_7d)

# Function to handle Telegram updates
def handle_telegram_updates(updates):
    for update in updates.get("result", []):
        message = update.get("message", {})
        text = message.get("text", "")
        chat_id = message.get("chat", {}).get("id", "")

        if text == "/projection" and str(chat_id) == CHAT_ID:
            main()  # Run the main function when the command is received

# Fetch updates from Telegram
def fetch_telegram_updates(offset=None):
    url = f"{TELEGRAM_API_URL}getUpdates"
    params = {"timeout": 100, "offset": offset}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching updates: {e}")
        return {}

# Main function to fetch data and analyze
def main():
    for symbol in COINS:
        df = fetch_data(symbol)
        if df.empty:
            print(f"No data available for {symbol}.")
            continue
        df = calculate_indicators(df)
        analyze_data(df, symbol)

if __name__ == "__main__":
    last_update_id = None
    while True:
        updates = fetch_telegram_updates(last_update_id)
        if updates.get("result"):
            last_update_id = updates["result"][-1]["update_id"] + 1
        handle_telegram_updates(updates)
        time.sleep(1)