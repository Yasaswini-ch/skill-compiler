---
name: recipe-scaler
description: Scale a short recipe to a new number of servings and print the result as a fixed table.
---

# Recipe scaler

1. Read the original number of servings and the target number of servings.
2. Compute the scale factor as target servings divided by original servings.
3. List each ingredient with its original quantity and unit, exactly as written in the recipe.
4. Multiply each original quantity by the scale factor.
5. Show every scaled quantity with exactly 1 decimal place, keeping the original unit.
6. If a scaled quantity in grams is 1000 or more, show it in kg instead (divide by 1000) with exactly 1 decimal place.
7. Output a Markdown table whose first line is exactly "| Ingredient | Original | Scaled |", followed by a separator line and one row per ingredient, in the order of the recipe.
8. After the table, write one last line "Scale factor: " followed by the factor. Write nothing before the table and nothing after this line.
