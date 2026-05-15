from __future__ import annotations

import hashlib
from typing import Any


COOK_AT_HOME_RECIPES: tuple[dict[str, str], ...] = (
    {
        "title": "Chicken Rice Power Bowl",
        "fit_reason": "Lean protein and easy carbs support recovery after high-output sessions.",
        "source_link": "https://www.budgetbytes.com/chicken-rice-bowls/",
    },
    {
        "title": "Salmon Sweet Potato Plate",
        "fit_reason": "Balances protein, potassium, and steady carbs for mixed training days.",
        "source_link": "https://www.eatingwell.com/recipe/269730/roasted-salmon-sweet-potatoes/",
    },
    {
        "title": "Turkey Pasta Skillet",
        "fit_reason": "Adds dense carbs and protein for tough conditioning days.",
        "source_link": "https://www.skinnytaste.com/turkey-pasta-skillet/",
    },
    {
        "title": "Greek Yogurt Overnight Oats",
        "fit_reason": "Useful for early sessions when you need digestible fuel ahead of time.",
        "source_link": "https://www.loveandlemons.com/overnight-oats-recipe/",
    },
    {
        "title": "Steak Burrito Bowl",
        "fit_reason": "Covers higher calorie demands with protein, rice, and micronutrient-rich toppings.",
        "source_link": "https://www.feastingathome.com/burrito-bowl/",
    },
    {
        "title": "Tofu Teriyaki Rice Bowl",
        "fit_reason": "Vegetarian-friendly protein with fast glycogen support from rice.",
        "source_link": "https://www.noracooks.com/teriyaki-tofu/",
    },
    {
        "title": "Egg Potato Breakfast Scramble",
        "fit_reason": "Works well for lower-volume days that still need solid protein and satiety.",
        "source_link": "https://www.spendwithpennies.com/breakfast-skillet/",
    },
    {
        "title": "Shrimp Couscous Meal Prep",
        "fit_reason": "Light but effective option when you want recovery fuel without a heavy meal.",
        "source_link": "https://www.themediterraneandish.com/shrimp-couscous/",
    },
    {
        "title": "Beef Chili With Rice",
        "fit_reason": "High-protein comfort meal that replenishes carbs and sodium after sweaty sessions.",
        "source_link": "https://www.wellplated.com/healthy-turkey-chili/",
    },
    {
        "title": "Protein Pancakes and Berries",
        "fit_reason": "Simple higher-carb recovery option when appetite is low after training.",
        "source_link": "https://feelgoodfoodie.net/recipe/protein-pancakes/",
    },
)


QUICK_ORDER_RECIPES: tuple[dict[str, str], ...] = (
    {
        "title": "Double Chicken Burrito Bowl",
        "fit_reason": "Easy fast-casual pick for protein, rice, and sodium after harder metcons.",
        "source_link": "https://www.chipotle.com/order",
    },
    {
        "title": "Salmon Greens and Grain Bowl",
        "fit_reason": "Good mixed-day option with protein, carbs, and lighter digestion.",
        "source_link": "https://www.sweetgreen.com/menu",
    },
    {
        "title": "Turkey Avocado Salad Bar Box",
        "fit_reason": "Higher protein lunch option when you want recovery without a heavy dinner.",
        "source_link": "https://www.panerabread.com/",
    },
    {
        "title": "Steak Rice and Veggie Plate",
        "fit_reason": "Supports strength-focused days with dense protein and refill carbs.",
        "source_link": "https://www.qdoba.com/order-online",
    },
    {
        "title": "Rotisserie Chicken and Potatoes",
        "fit_reason": "Reliable grocery pickup option when you need practical recovery fuel fast.",
        "source_link": "https://www.wholefoodsmarket.com/",
    },
    {
        "title": "Tuna Pasta Deli Combo",
        "fit_reason": "Convenient moderate-volume option with protein and quick-digesting carbs.",
        "source_link": "https://www.publix.com/",
    },
    {
        "title": "Tofu Grain Salad Bowl",
        "fit_reason": "Plant-forward order that still covers carbs and protein for training support.",
        "source_link": "https://www.cava.com/",
    },
    {
        "title": "Chicken Noodle Soup and Sandwich",
        "fit_reason": "Helpful when hydration and sodium matter as much as calories.",
        "source_link": "https://www.panerabread.com/",
    },
    {
        "title": "Greek Chicken Wrap Combo",
        "fit_reason": "Portable post-workout meal with solid protein and manageable fats.",
        "source_link": "https://www.zoeskitchen.com/",
    },
    {
        "title": "Egg White Breakfast Sandwich Set",
        "fit_reason": "Good early-day choice when you need something fast before or after training.",
        "source_link": "https://www.starbucks.com/menu",
    },
)


def _stable_index(seed_text: str, category: str, pool_size: int) -> int:
    digest = hashlib.sha256(f"{seed_text}:{category}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % pool_size


def select_recipes_deterministic(workout_date: str, archetype: str, intensity: str) -> list[dict[str, Any]]:
    seed_text = f"{workout_date}|{archetype}|{intensity}"
    cook_recipe = dict(COOK_AT_HOME_RECIPES[_stable_index(seed_text, "cook_at_home", len(COOK_AT_HOME_RECIPES))])
    quick_recipe = dict(QUICK_ORDER_RECIPES[_stable_index(seed_text, "quick_order_salad_bar", len(QUICK_ORDER_RECIPES))])
    cook_recipe["category"] = "cook_at_home"
    quick_recipe["category"] = "quick_order_salad_bar"
    return [cook_recipe, quick_recipe]