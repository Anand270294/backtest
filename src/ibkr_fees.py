import numpy as np


def calculate_ibkr_fixed_cost(qty, price_per_share):
    """Returns the fixed cost of IBKR for a given quantity and price per share."""
    cost_per_share = 0.005
    fixed_cost = qty * cost_per_share

    fixed_cost = max(1, min(fixed_cost, price_per_share * qty * 0.01))

    # Regulatory Fees
    sec_transaction_fee = 0.0000278 * price_per_share * qty
    finra_trading_activity_fee = min(0.000166 * qty, 8.30)

    final_fees = fixed_cost + sec_transaction_fee + finra_trading_activity_fee

    return final_fees


def calculate_ibkr_tiered_cost(current_month_vol, qty, price):
    """Returns the tiered cost of IBKR for a given quantity, price, and current month volume."""
    price_dict = {
        300000: 0.0035,
        3000000: 0.002,
        20000000: 0.0015,
        100000000: 0.001,
        np.inf: 0.0005,
    }

    cost = 0
    remaining_qty = qty
    while remaining_qty > 0:
        for key, value in price_dict.items():
            if current_month_vol < key:
                cost_per_share = value
                if current_month_vol + remaining_qty <= key:
                    cost += remaining_qty * cost_per_share
                    remaining_qty = 0
                    break

                remaining_vol_in_tier = key - current_month_vol
                remaining_qty -= remaining_vol_in_tier
                cost += remaining_vol_in_tier * cost_per_share
                current_month_vol += remaining_vol_in_tier
                break

    cost = max(0.35, min(cost, price * qty * 0.01))

    # Regulatory Fees
    sec_transaction_fee = 0.0000278 * price * qty
    finra_trading_activity_fee = 0.000166 * qty

    # Exchange Fees
    exchange_fees = 0.003 * qty

    # Clearing Fees
    clearing_fees = min(0.00020 * qty, qty * price * 0.005)

    # Pass Through Fees
    nyse_pass_through_fees = (sec_transaction_fee + finra_trading_activity_fee + exchange_fees + clearing_fees) * 0.000175
    finra_pass_through_fees = min(
        (sec_transaction_fee + finra_trading_activity_fee + exchange_fees + clearing_fees) * 0.000565,
        8.30,
    )

    total_fees = (
        sec_transaction_fee
        + finra_trading_activity_fee
        + exchange_fees
        + clearing_fees
        + nyse_pass_through_fees
        + finra_pass_through_fees
        + cost
    )

    return total_fees
