# meridian-bank-of-canada

The Bank of Canada's public rates for [Open Meridian](https://open-meridian.com):
an Open Meridian plugin that puts CORRA, its compounded index and the policy
rate, the Government of Canada benchmark bond yields, the Bank's
zero-coupon yield curve, and its daily exchange rates into a deployment's
lake. It reads the Bank's Valet API and its curve files, and holds the
`data` role, a data plugin. This is release 0.1.0, a draft for the product
owner. How to set it up and use it is in [docs/](docs/README.md).

It is built on the SDK it pins, `open-meridian==0.37.1` (contract 30).

## What it records

- **`<instance>:boc_rates`:** CORRA, each day's `fixing` with its 25th and
  75th percentiles and its volume; the CORRA Compounded Index, an index
  level based 12 June 2020 = 100; the target for the overnight rate, a
  `fixing`. In per cent, actual/365 simple: the Canadian money market's
  convention, the plugin's statement, since the Bank states only per cent.
- **`<instance>:boc_curves`:** the 2, 3, 5, 7 and 10-year benchmark bond
  yields, each a benchmark yield at its tenor on one curve record,
  semi-annual bond-equivalent. The long-term benchmark and the Real Return
  Bonds' yield are not carried.
- **`<instance>:boc_curves`, too:** the zero-coupon curve, 120 zero rates from 3
  months to 30 years, made per cent exactly from the Bank's decimals,
  continuously compounded; published weekly with a two-week lag. No forward
  rates or model parameters.
- **`<instance>:boc_fx`:** each currency's daily rate, the price of its cash
  instrument in Canadian dollars, as the Bank states it, never inverted.
- **Records:** CORRA, its index, the policy rate and the two curves are each
  asked of the deployment by a code at `boc` (`boc:CORRA`); the platform
  seeds none yet, so each is reported missing, never minted, and its rates
  wait. Each currency resolves by its ISO 4217 code.
- **Not presented:** the Bank's auction results, until the contract holds
  an auction kind. No published time is recorded: the Bank states none.

## Deploying it

On a deployment, with the `meridian` CLI connected (`meridian connect`):

    meridian plugin upload                  # from this directory
    meridian plugin launch bank-of-canada   # a deployment admin approves its one role, data

No key and no account. A deployment admin then licenses its three datasets
and entitles the plugins that read them on the Data sources page
([docs/setup.md](docs/setup.md)).

## Checking it

    make ci-local                  # lint, tests, plugin check, image, e2e: the pre-push gate
    make preview SHOTS=<dir>       # each page in a browser with the kit, at 375, 582 and 1280 px

`tests/test_suite.py` runs the SDK's data suite on the plugin's own
conversion, and it passes; a case about what the Bank never states here is
not presented, with why.

## The terms, summarised

Not legal advice; read the Bank's own words
([terms](https://www.bankofcanada.ca/terms/)) before relying on them. The
Bank allows its content to be used, copied and distributed with credit to
the Bank and a note of any changes, implying no endorsement; a paid service
including it must tell its buyers it is free on the Bank's website;
third-party content is excluded unless marked; its request limits may not be
circumvented; its exchange rates are not meant as a benchmark for executing
foreign exchange trades. Each dataset says so in words, and declares no
licence: the deployment admin's licence is the one enforced. This project is
not affiliated with or endorsed by the Bank of Canada.

## Licence

Apache-2.0 (LICENSE, NOTICE). The Bank's answers under
`src/bank_of_canada/responses/` are as received on 2026-11-19.
