import pandas as pd
import numpy as np

from sklearn.preprocessing import StandardScaler
from sklearn.metrics.pairwise import cosine_similarity


# =========================================
# MARKET ANALOG ENGINE V1
# =========================================

def calculate_rsi(series, period=14):
    delta = series.diff()

    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    rsi = 100 - (100 / (1 + rs))

    return rsi


def calculate_obv(close, volume):
    obv = [0]

    for i in range(1, len(close)):
        if close.iloc[i] > close.iloc[i - 1]:
            obv.append(obv[-1] + volume.iloc[i])

        elif close.iloc[i] < close.iloc[i - 1]:
            obv.append(obv[-1] - volume.iloc[i])

        else:
            obv.append(obv[-1])

    return pd.Series(obv, index=close.index)


# =========================================
# BUILD FEATURES
# =========================================

def build_market_features(df):

    df = df.copy()

    df["Return"] = df["Close"].pct_change()

    df["EMA9"] = df["Close"].ewm(span=9).mean()

    df["MA20"] = df["Close"].rolling(20).mean()

    df["Stretch"] = (
        (df["Close"] - df["MA20"]) / df["MA20"]
    )

    df["RSI"] = calculate_rsi(df["Close"])

    df["OBV"] = calculate_obv(df["Close"], df["Volume"])

    df["OBV_EMA9"] = df["OBV"].ewm(span=9).mean()

    df["OBV_DIFF"] = (
        (df["OBV"] - df["OBV_EMA9"])
        / abs(df["OBV_EMA9"])
    )

    df["Slope_EMA9"] = df["EMA9"].pct_change(3)

    return df.dropna()


# =========================================
# CREATE WINDOW VECTOR
# =========================================

def create_window_vector(df_window):

    features = [
        "Return",
        "Stretch",
        "RSI",
        "OBV_DIFF",
        "Slope_EMA9"
    ]

    vectors = []

    for col in features:

        arr = df_window[col].values.reshape(-1, 1)

        scaler = StandardScaler()

        arr_scaled = scaler.fit_transform(arr)

        vectors.extend(arr_scaled.flatten())

    return np.array(vectors)


# =========================================
# FIND SIMILAR PERIODS
# =========================================

def find_similar_periods(
    df,
    window=40,
    top_k=5
):

    df = build_market_features(df)

    current_window = df.iloc[-window:]

    current_vector = create_window_vector(
        current_window
    )

    results = []

    for i in range(
        0,
        len(df) - window - 10
    ):

        hist_window = df.iloc[i:i + window]

        hist_vector = create_window_vector(
            hist_window
        )

        similarity = cosine_similarity(
            [current_vector],
            [hist_vector]
        )[0][0]

        future_5d = (
            df.iloc[i + window + 5]["Close"]
            / df.iloc[i + window]["Close"]
            - 1
        )

        future_10d = (
            df.iloc[i + window + 10]["Close"]
            / df.iloc[i + window]["Close"]
            - 1
        )

        results.append({

            "Start":
                hist_window.index[0],

            "End":
                hist_window.index[-1],

            "Similarity":
                round(similarity, 4),

            "Future_5D":
                round(future_5d * 100, 2),

            "Future_10D":
                round(future_10d * 100, 2),
        })

    result_df = pd.DataFrame(results)

    result_df = result_df.sort_values(
        "Similarity",
        ascending=False
    )

    return result_df.head(top_k)


# =========================================
# NAV SUGGESTION
# =========================================

def generate_market_prediction(
    result_df
):

    avg_5d = result_df["Future_5D"].mean()

    avg_10d = result_df["Future_10D"].mean()

    confidence = (
        result_df["Similarity"].mean()
        * 100
    )

    if avg_10d > 3:

        regime = "RISK ON"

        nav = "70-100%"

    elif avg_10d > 0:

        regime = "TRUNG TÍNH"

        nav = "40-70%"

    else:

        regime = "RISK OFF"

        nav = "0-30%"

    return {

        "confidence":
            round(confidence, 2),

        "avg_5d":
            round(avg_5d, 2),

        "avg_10d":
            round(avg_10d, 2),

        "regime":
            regime,

        "nav":
            nav
    }
