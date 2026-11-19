# Setup

## Launching it

The Bank's data need no key and no account. Launch the plugin and approve its
one role, `data`. It reads the Bank at once, and every hour after.

Its settings: the **Raw responses window** and **past the window** (the
SDK's), and on a deployment installed for development, **Sample data**: the
Bank's answers recorded on 19 November 2026, committed with the plugin.

## Its datasets

On the deployment's **Data sources** page (deployment admins), for each of
`<instance>:boc_rates`, `<instance>:boc_curves` and `<instance>:boc_fx`:

1. **License it.** Each dataset describes the Bank's terms in words and
   declares no licence: credit to the Bank, a note of any change, no
   endorsement implied, and a paid service including it tells its buyers it
   is free on the Bank's website. The exchange rates are not meant as a
   benchmark for executing trades. Until a licence is set, the lake keeps the
   rows and reads every use right restrictively.
2. **Entitle** each plugin that reads it.
3. **Priority**, where another dataset states the same values.

## The records

CORRA, its index, the policy rate and the two curves are each about a record
named by a code at `boc`: `boc:CORRA`, `boc:CORRA compounded index`,
`boc:Target for the overnight rate`, `boc:Benchmark bond yields`,
`boc:Zero-coupon yield curve`. The platform does not seed them yet, and the
plugin never makes one: the Datasets page's Records tab shows each as not
held, and its values wait until your deployment holds it. Each currency is
found by its ISO 4217 code.
