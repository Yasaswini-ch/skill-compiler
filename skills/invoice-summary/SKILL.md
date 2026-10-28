---
name: invoice-summary
description: Read a short supplier invoice and compute its subtotal, discount, tax and total.
---

# Invoice summary

1. Extract the vendor name.
2. Extract the invoice number. Write it as "INV-" followed by the digits only.
3. List every line item with its quantity and unit price.
4. Compute each line total as quantity multiplied by unit price.
5. Compute the subtotal as the sum of all line totals.
6. If the subtotal is greater than 200.00, the discount is 10% of the subtotal, rounded to 2 decimals. Otherwise the discount is 0.00.
7. Compute the tax as 8% of (subtotal minus discount), rounded to 2 decimals.
8. Compute the total as subtotal minus discount plus tax.
9. Output JSON with exactly these keys: vendor, invoice, subtotal, discount, tax, total. Write every amount as a string with exactly 2 decimals and no currency symbol.
