"""
Search API Router.

Centralizes search logic for Food (Dish/Product) and Global content (Dialogues/Cards).
Refactored to use atomic services: ProductSearchService, DishSearchService, etc.
"""
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends
from apps.deps import get_current_user_id, require_auth
from apps.settings import BackendSettings
from apps.common.dialogue_service import DialogueService
from apps.common.search_services import (
    ProductSearchService,
    DishSearchService,
    CardSearchService,
    DialogueSearchService
)


def build_search_router(settings: BackendSettings) -> APIRouter:
    # Initialize auth dependency with settings
    auth_dep = require_auth(settings)
    
    # Define dependency specifically for this router's scope
    def get_dialogue_service(user_id: str = Depends(get_current_user_id)) -> DialogueService:
        return DialogueService(user_id)

    router = APIRouter()

    @router.get("/api/search/food", dependencies=[Depends(auth_dep)])
    async def search_food(
        q: Optional[str] = "",
        user_id: str = Depends(get_current_user_id)
    ):
        """
        [Consumer: Add Dish / Edit Name]
        Purpose: Find Food Data (Product, Dish)
        Query:
          - q is Empty: Return Recommendations (Top 5 Products, Top 5 Aggregated Dishes)
          - q is Typed: Return Search Results (Products + Aggregated Dishes)
        """
        product_service = ProductSearchService(user_id)
        dish_service = DishSearchService(user_id)

        query = (q or "").strip()

        if not query:
            # Scenario: Recommendation
            try:
                products = product_service.get_recommendations(limit=5)
                product_items = [{"type": "product", "data": p} for p in products]
            except Exception:
                product_items = []

            try:
                dishes = dish_service.get_recommendations(limit=5)
                dish_items = [{"type": "dish", "data": d} for d in dishes]
            except Exception:
                dish_items = []

            return product_items + dish_items
        else:
            # Scenario: Search
            try:
                products = product_service.search(query, limit=5)
                product_items = [{"type": "product", "data": p} for p in products]
            except Exception:
                product_items = []
            
            try:
                dishes = dish_service.search_aggregated(query, limit=20)
                dish_items = [{"type": "dish", "data": d} for d in dishes]
            except Exception:
                dish_items = []

            # Combine
            return product_items + dish_items

    @router.get("/api/search/global", dependencies=[Depends(auth_dep)])
    async def search_global(
        q: Optional[str] = "",
        user_id: str = Depends(get_current_user_id),
        service: DialogueService = Depends(get_dialogue_service)
    ):
        """
        [Consumer: Sidebar Main Search]
        Purpose: Find Context (Cards, Dialogues) + Quick Actions (Products)
        """
        # Note: ProductSearchService needs user_id, others need DialogueService
        product_service = ProductSearchService(user_id)
        card_service = CardSearchService(service)
        dialogue_service = DialogueSearchService(service)

        query = (q or "").strip()

        if not query:
            # Scenario: Sidebar Empty State / Recommendations
            # Return Top Products + Recent Saved Cards
            try:
                # Top 5 Product Recs
                products = product_service.get_recommendations(limit=5)
            except Exception:
                products = []
            
            try:
                # Top 10 Saved Cards (History)
                cards = card_service.search_history(query="", limit=5, saved_only=True)
            except Exception:
                cards = []

            return {
                "products": products,
                "cards": cards,
                "dialogues": [] # Usually no dialogues for empty state
            }

        # Scenario: Typed Search
        try:
            products = product_service.search(query, limit=5) 
        except Exception:
            products = []
            
        try:
            cards = card_service.search_history(query, limit=10, saved_only=False)
        except Exception:
            cards = []
            
        try:
            dialogues = dialogue_service.search(query, limit=10)
        except Exception:
            dialogues = []

        return {
            "products": products,
            "cards": cards,
            "dialogues": dialogues
        }

    @router.get("/api/search/recent_saved_card", dependencies=[Depends(auth_dep)])
    async def get_recent_saved_card(
        limit: int = 10,
        service: DialogueService = Depends(get_dialogue_service),
    ):
        """
        [Consumer: Sidebar Recents / History]
        Purpose: Get Saved Cards for quick reuse.
        """
        card_service = CardSearchService(service)
        # Use empty query with saved_only=True to get recent saved
        return card_service.search_history(query="", limit=limit, saved_only=True)

    return router
