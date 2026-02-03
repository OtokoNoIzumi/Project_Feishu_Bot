"""公共能力模块，比如对话、session"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Body
from apps.deps import get_current_user_id, require_auth
from apps.settings import BackendSettings
from apps.common.dialogue_service import DialogueService
from apps.common.models.dialogue import Dialogue, DialogueMessage, ResultCard
from libs.storage_lib import global_storage


def build_dialogue_router(settings: BackendSettings) -> APIRouter:
    """构建对话路由"""
    router = APIRouter()
    auth_dep = require_auth(settings)

    def get_service(user_id: str = Depends(get_current_user_id)) -> DialogueService:
        return DialogueService(user_id)

    # ========== Dialogue APIs ==========

    @router.get(
        "/api/dialogues",
        response_model=List[Dialogue],
        dependencies=[Depends(auth_dep)],
    )
    async def list_dialogues(
        limit: int = 20,
        offset: int = 0,
        service: DialogueService = Depends(get_service),
    ):
        """List dialogues sorted by last updated."""
        return service.list_dialogues(limit, offset)

    @router.post(
        "/api/dialogues", response_model=Dialogue, dependencies=[Depends(auth_dep)]
    )
    async def create_dialogue(
        title: str = Body(..., embed=True),
        service: DialogueService = Depends(get_service),
    ):
        """Create a new empty dialogue."""
        return service.create_dialogue(title)

    @router.get(
        "/api/dialogues/{dialogue_id}",
        response_model=Dialogue,
        dependencies=[Depends(auth_dep)],
    )
    async def get_dialogue(
        dialogue_id: str, service: DialogueService = Depends(get_service)
    ):
        dialogue = service.get_dialogue(dialogue_id)
        if not dialogue:
            raise HTTPException(status_code=404, detail="Dialogue not found")
        return dialogue

    @router.patch(
        "/api/dialogues/{dialogue_id}/message",
        response_model=Dialogue,
        dependencies=[Depends(auth_dep)],
    )
    async def append_message(
        dialogue_id: str,
        message: DialogueMessage,
        service: DialogueService = Depends(get_service),
    ):
        """Append a message to a dialogue."""
        dialogue = service.append_message(dialogue_id, message)
        if not dialogue:
            raise HTTPException(status_code=404, detail="Dialogue not found")
        return dialogue

    @router.patch(
        "/api/dialogues/{dialogue_id}/messages/{message_id}",
        response_model=Dialogue,
        dependencies=[Depends(auth_dep)],
    )
    async def update_message(
        dialogue_id: str,
        message_id: str,
        message: DialogueMessage,
        service: DialogueService = Depends(get_service),
    ):
        """Update a specific message (e.g. backfill attachments)."""
        if message.id != message_id:
            raise HTTPException(status_code=400, detail="ID mismatch")

        dialogue = service.update_message(dialogue_id, message)
        if not dialogue:
            raise HTTPException(status_code=404, detail="Dialogue or message not found")
        return dialogue

    @router.patch(
        "/api/dialogues/{dialogue_id}",
        response_model=Dialogue,
        dependencies=[Depends(auth_dep)],
    )
    async def update_dialogue(
        dialogue_id: str,
        title: str = Body(None, embed=True),
        user_title: str = Body(None, embed=True),
        service: DialogueService = Depends(get_service),
    ):
        """Rename a dialogue."""
        dialogue = service.get_dialogue(dialogue_id)
        if not dialogue:
            raise HTTPException(status_code=404, detail="Dialogue not found")

        if title is not None:
            dialogue.title = title
        if user_title is not None:
            dialogue.user_title = user_title

        return service.update_dialogue(dialogue)

    @router.delete("/api/dialogues/{dialogue_id}", dependencies=[Depends(auth_dep)])
    async def delete_dialogue(
        dialogue_id: str, service: DialogueService = Depends(get_service)
    ):
        success = service.delete_dialogue(dialogue_id)
        if not success:
            raise HTTPException(status_code=404, detail="Dialogue not found")
        return {"success": True}

    # ========== ResultCard APIs ==========

    @router.get(
        "/api/cards", response_model=List[ResultCard], dependencies=[Depends(auth_dep)]
    )
    async def list_cards(
        dialogue_id: str = None, service: DialogueService = Depends(get_service)
    ):
        """List result cards, optionally filtered by dialogue ID."""
        return service.list_cards(dialogue_id)

    @router.get(
        "/api/cards/recent",
        response_model=List[ResultCard],
        dependencies=[Depends(auth_dep)],
    )
    async def get_recent_cards(service: DialogueService = Depends(get_service)):
        """Get recent cards for sidebar display."""
        return service.get_sidebar_recent_cards()

    @router.post(
        "/api/cards", response_model=ResultCard, dependencies=[Depends(auth_dep)]
    )
    async def create_card(
        card: ResultCard,
        service: DialogueService = Depends(get_service),
        user_id: str = Depends(get_current_user_id),
    ):
        """Create a new result card (e.g. from analysis result)."""
        # Enforce user ownership
        card.user_id = user_id

        # Save card
        saved_card = service.save_card(card)

        # Update dialogue association
        if card.dialogue_id:
            dialogue = service.get_dialogue(card.dialogue_id)
            if dialogue:
                if card.id not in dialogue.card_ids:
                    dialogue.card_ids.append(card.id)
                    service.update_dialogue(dialogue)

        return saved_card

    @router.get(
        "/api/cards/{card_id}",
        response_model=ResultCard,
        dependencies=[Depends(auth_dep)],
    )
    async def get_card(card_id: str, service: DialogueService = Depends(get_service)):
        card = service.get_card(card_id)
        if not card:
            raise HTTPException(status_code=404, detail="Card not found")
        return card

    @router.patch(
        "/api/cards/{card_id}",
        response_model=ResultCard,
        dependencies=[Depends(auth_dep)],
    )
    async def update_card(
        card_id: str,
        card_update: ResultCard,  # Accept full model for now, could be Partial
        service: DialogueService = Depends(get_service),
    ):
        """Update a card state/content."""
        # Check existence first
        existing = service.get_card(card_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Card not found")

        # Ensure ID matches
        if card_update.id != card_id:
            raise HTTPException(status_code=400, detail="ID mismatch")

        return service.save_card(card_update)

    @router.get("/api/search/global", dependencies=[Depends(auth_dep)])
    async def search_global(
        q: str,
        user_id: str = Depends(get_current_user_id),
        service: DialogueService = Depends(get_service),
    ):
        q = q.lower().strip()
        if len(q) < 1:
            return {"products": [], "cards": [], "dialogues": []}

        products = global_storage.read_dataset(
            user_id, "diet", "product_library.jsonl", limit=2000
        )
        product_matches = []
        seen_prod = set()
        for p in products:
            pname = str(p.get("product_name", "")).lower()
            if q in pname:
                key = (p.get("product_name"), p.get("brand"))
                if key not in seen_prod:
                    seen_prod.add(key)
                    product_matches.append(p)
                    if len(product_matches) >= 5:
                        break

        # 2. Cards (Raw History) using Index
        card_matches = []
        sorted_index = sorted(
            service.card_index, key=lambda x: x["updated_at"], reverse=True
        )

        c_count = 0
        for c in sorted_index:
            if c.get("mode") and c.get("mode") != "diet":
                continue
            matched = False
            if c.get("user_title") and q in c["user_title"].lower():
                matched = True
            elif c.get("meal_name") and q in c["meal_name"].lower():
                matched = True
            else:
                for dn in c.get("dish_names", []):
                    if q in dn.lower():
                        matched = True
                        break

            if matched:
                card_matches.append(c)
                c_count += 1
                if c_count >= 10:
                    break

        # 3. Dialogues
        dialogue_matches = []
        sorted_dialogues = sorted(
            service.dialogue_index, key=lambda x: x["updated_at"], reverse=True
        )
        d_count = 0
        for d in sorted_dialogues:
            if d.get("title") and q in d["title"].lower():
                dialogue_matches.append(d)
                d_count += 1
                if d_count >= 10:
                    break

        return {
            "products": product_matches,
            "cards": card_matches,
            "dialogues": dialogue_matches,
        }

    return router
