# Position Types

LONG_POSITION = "long"
SHORT_POSITION = "short"

# Order Types
MARKET_ORDER = "Market"
LIMIT_ORDER = "Limit"
STOP_ORDER = "Stop"
STOP_LIMIT_ORDER = "Stop Limit"
TRAILING_STOP_ORDER = "Trailing Stop"
TRAILING_STOP_LIMIT_ORDER = "Trailing Stop Limit"

# Trail Types
TRAIL_TYPE_VALUE = "Value"
TRAIL_TYPE_PERCENTAGE = "Percentage"

# Order Status
ORDER_STATUS_FILLED = "Filled"
ORDER_STATUS_CANCELLED = "Cancelled"
ORDER_STATUS_PENDING = "Pending"
ORDER_STATUS_EXPIRED = "Expired"
ORDER_STATUS_SPLIT_ADJ = "Split Adjustment"

# Trade Status
TRADE_STATUS_OPEN = "Open"
TRADE_STATUS_CLOSED = "Closed"

# Trade Actions
TRADE_ACTION_BUY = "Buy"
TRADE_ACTION_SELL = "Sell"

# Time in Force
TIME_IN_FORCE_DAY = "Day"
TIME_IN_FORCE_GTC = "Good Till Cancelled"


# Stop Loss Triggers
STOP_LOST_TRIGGERS = [TRAILING_STOP_ORDER, TRAILING_STOP_LIMIT_ORDER, STOP_ORDER, STOP_LIMIT_ORDER]
