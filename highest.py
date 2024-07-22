import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time

# Telegram Bot Configuration
CHAT_ID = ''
TELEGRAM_API_URL = "https://api.telegram.org/bot/"
COINGECKO_API_URL = "https://api.coingecko.com/api/v3/coins/"

# List of known stablecoins to exclude
STABLECOINS = ["tether", "usd-coin", "binance-usd", "dai", "paxos-standard", "true-usd"]

# Helper functions
def fetch_top_coins():
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            'vs_currency': 'usd',
            'order': 'market_cap_desc',
            'per_page': 10,
            'page': 1,
            'sparkline': False
        }
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching top coins: {e}")
        return []

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
        return None, None  # Skip analysis if DataFrame is empty

    latest = df.iloc[-1]
    future_prices_up_8h = df['price'].rolling(window=48).apply(lambda x: x.iloc[-1] * 1.10)  # 10% increase over 8 hours
    future_prices_down_8h = df['price'].rolling(window=48).apply(lambda x: x.iloc[-1] * 0.90)  # 10% decrease over 8 hours
    projected_price_up_8h = future_prices_up_8h.iloc[-1]
    projected_price_down_8h = future_prices_down_8h.iloc[-1]

    future_prices_up_7d = df['price'].rolling(window=336).apply(lambda x: x.iloc[-1] * 1.10)  # 10% increase over 7 days
    future_prices_down_7d = df['price'].rolling(window=336).apply(lambda x: x.iloc[-1] * 0.90)  # 10% decrease over 7 days
    projected_price_up_7d = future_prices_up_7d.iloc[-1]
    projected_price_down_7d = future_prices_down_7d.iloc[-1]

    # Calculate percentage change for 8 hours
    if not np.isnan(projected_price_up_8h) and latest['price'] != 0:
        profit_percentage_8h = ((projected_price_up_8h - latest['price']) / latest['price']) * 100
    else:
        profit_percentage_8h = None

    # Calculate percentage change for 7 days
    if not np.isnan(projected_price_up_7d) and latest['price'] != 0:
        profit_percentage_7d = ((projected_price_up_7d - latest['price']) / latest['price']) * 100
    else:
        profit_percentage_7d = None

    return profit_percentage_8h, profit_percentage_7d

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
    top_coins = fetch_top_coins()
    best_coin = None
    best_profit_8h = -np.inf
    best_profit_7d = -np.inf

    for coin in top_coins:
        symbol = coin['id']
        if symbol in STABLECOINS:
            continue  # Skip stablecoins
        df = fetch_data(symbol)
        if df.empty:
            print(f"No data available for {symbol}.")
            continue
        df = calculate_indicators(df)
        profit_8h, profit_7d = analyze_data(df, symbol)

        if profit_8h and profit_8h > best_profit_8h:
            best_profit_8h = profit_8h
            best_coin = symbol
        if profit_7d and profit_7d > best_profit_7d:
            best_profit_7d = profit_7d
            best_coin = symbol

    if best_coin:
        message = (f"The best potential high return coin is {best_coin.capitalize()}.\n"
                   f"Projected profit in the next 8 hours: {best_profit_8h:.2f}%\n"
                   f"Projected profit in the next 7 days: {best_profit_7d:.2f}%")
        send_telegram_message(message)

if __name__ == "__main__":
    last_update_id = None
    while True:
        updates = fetch_telegram_updates(last_update_id)
        if updates.get("result"):
            last_update_id = updates["result"][-1]["update_id"] + 1
        handle_telegram_updates(updates)
        time.sleep(1)