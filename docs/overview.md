# Overview

The Bank of Canada publishes the rates this plugin puts into your
deployment's lake:

- **CORRA, its compounded index and the policy rate**
  (`<instance>:boc_rates`): CORRA each business day, with its 25th and 75th
  percentiles and its volume; the CORRA Compounded Index, based 12 June 2020
  = 100; and the target for the overnight rate.
- **Benchmark bond yields** (`<instance>:boc_curves`): the Government of
  Canada's 2, 3, 5, 7 and 10-year benchmark bonds' yields, each at its tenor
  on one curve.
- **The zero-coupon curve** (`<instance>:boc_curves`, beside the benchmark yields): the Bank's
  Government of Canada zero-coupon curve, 120 points from 3 months to 30
  years, published weekly with a two-week lag.
- **Exchange rates** (`<instance>:boc_fx`): each currency's daily rate, the
  price of one unit of it in Canadian dollars.

It reads the Bank's public website: no key, no account. It checks for new
values every hour, and reads any past day the lake asks for.

## What it records

- **Each value as the Bank writes it,** made an exact decimal from its text;
  the zero curve's decimals (0.0251821 is 2.51821%) made per cent exactly.
  A day the Bank states nothing for is no value, never a zero.
- **Conventions.** The Bank states its rates in per cent and no day count;
  the plugin states CORRA, its index and the policy rate actual/365 simple
  (the Canadian money market's), the benchmark yields semi-annual
  bond-equivalent, and the zero curve continuously compounded.
- **Against your deployment's records.** CORRA, its index, the policy rate
  and the two curves are each asked of your deployment by a code at `boc`;
  the plugin never makes a record: one your deployment does not hold is
  reported missing, and its values wait. Each currency is found by its ISO
  4217 code.
- **No published time:** the Bank states none on a value.
- **Not carried:** the long-term benchmark bond (the Bank states no tenor
  for it), the Real Return Bonds' yield, and the Bank's auction results.

## What it never does

It records no trade and shows no value on its pages. It holds no account and
uses no key. Its exchange rates are never inverted.
