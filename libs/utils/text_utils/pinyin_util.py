
import re
import pypinyin
import itertools
from typing import List, Dict, Any

# Common polyphonic characters mapping: character -> [main pronunciation, alternative pronunciation]
common_polyphonic = {
    "的": ["de", "di"],
    "着": ["zhe", "zhao"],
    "了": ["le", "liao"],
    "还": ["hai", "huan"],
    "都": ["dou", "du"],
    "会": ["hui", "kuai"],
    "没": ["mei", "mo"],
    "重": ["zhong", "chong"],
    "长": ["chang", "zhang"],
    "地": ["di", "de"],
    "行": ["xing", "hang"],
    "种": ["zhong", "chong"],
    "大": ["da", "dai"],
    "单": ["dan", "shan"],
    "解": ["jie", "xie"],
}

# Contextual rules: specific pronunciations for specific words
context_rules = {
    "便": {
        "坐便": "bian",
        "方便": "bian",
        "便宜": "pian",
    }
}

def extract_phonetics(text: str) -> Dict[str, List[str]]:
    """
    Extract pinyin information from text for search matching.
    Copied logic from Module.Common.scripts.common.translation.extract_phonetics
    to avoid heavy dependencies like pandas.

    Strategy:
    1. Prefer most common pronunciation (lazy_pinyin).
    2. Add alternative pronunciations only for common polyphonic characters.
    3. Strictly control number of combinations to avoid obscure pronunciations.

    Args:
        text (str): Input text.

    Returns:
        dict: Dictionary containing 'pinyin_initials' and 'pinyin_full_list'.
    """
    if not text or not isinstance(text, str):
        return {"pinyin_initials": [], "pinyin_full_list": []}

    # 1. Normalize: keep Chinese and English, ignore punctuation/spaces/numbers
    normalized_chars = []
    for char in text:
        if re.match(r"[\u4e00-\u9fa5]", char):  # Chinese
            normalized_chars.append(char)
        elif re.match(r"[a-zA-Z]", char):  # English
            normalized_chars.append(char.lower())

    if not normalized_chars:
        return {"pinyin_initials": [], "pinyin_full_list": []}

    normalized_text = "".join(normalized_chars)

    # 2. Separate Chinese and English parts
    parts = re.findall(r"[\u4e00-\u9fa5]+|[a-z]+", normalized_text)

    part_results = []

    for part in parts:
        if re.match(r"[\u4e00-\u9fa5]+", part):  # Chinese part
            # Check context rules first
            context_applied = False
            part_initials = []
            part_full = []

            for char in context_rules:
                if char in part:
                    for word, fixed_pinyin in context_rules[char].items():
                        if word == part:  # Exact match for special word
                            # Calculate result for fixed pronunciation
                            other_chars = part.replace(char, "")
                            if other_chars:
                                other_pinyins = pypinyin.lazy_pinyin(
                                    other_chars, style=pypinyin.NORMAL, strict=False
                                )
                                other_initials = "".join(
                                    [py[0] for py in other_pinyins]
                                )
                                other_full = "".join(other_pinyins)

                                # Insert fixed pronunciation at correct position
                                char_pos = part.index(char)
                                if char_pos == 0:  # Char at start
                                    part_initials = [fixed_pinyin[0] + other_initials]
                                    part_full = [fixed_pinyin + other_full]
                                else:  # Char at end (assuming 2-char word)
                                    part_initials = [other_initials + fixed_pinyin[0]]
                                    part_full = [other_full + fixed_pinyin]
                            else:
                                # Single char
                                part_initials = [fixed_pinyin[0]]
                                part_full = [fixed_pinyin]
                            context_applied = True
                            break
                if context_applied:
                    break

            if not context_applied:
                # Use default logic
                main_pinyins = pypinyin.lazy_pinyin(
                    part, style=pypinyin.NORMAL, strict=False
                )
                main_initials = "".join([py[0] for py in main_pinyins])
                main_full = "".join(main_pinyins)

                # Check for common polyphonic characters
                alternative_initials = []
                alternative_full = []

                has_polyphonic = any(char in common_polyphonic for char in part)

                if has_polyphonic and len(part) <= 2:  # Only for short words
                    char_variants = []
                    for char in part:
                        if char in common_polyphonic:
                            char_variants.append(common_polyphonic[char][:2])
                        else:
                            main_char_pinyin = pypinyin.lazy_pinyin(
                                char, style=pypinyin.NORMAL, strict=False
                            )
                            char_variants.append(main_char_pinyin[:1])

                    # Generate combinations (max 2)
                    combinations = list(itertools.product(*char_variants))
                    if len(combinations) > 2:
                        combinations = combinations[:2]

                    for combo in combinations:
                        alt_initials = "".join([py[0] for py in combo])
                        alt_full = "".join(combo)
                        if alt_initials != main_initials:
                            alternative_initials.append(alt_initials)
                        if alt_full != main_full:
                            alternative_full.append(alt_full)

                # Combine results
                part_initials = [main_initials] + alternative_initials[:1]
                part_full = [main_full] + alternative_full[:1]

        else:  # English part
            # English: Initial = first char, Full = word
            part_initials = [part[0]] if part else [""]
            part_full = [part]

        part_results.append({"initials": part_initials, "full": part_full})

    # 3. Combine all parts
    final_initials = [""]
    final_full = [""]

    for part_result in part_results:
        new_initials = []
        new_full = []

        for existing_initial in final_initials:
            for part_initial in part_result["initials"]:
                new_initials.append(existing_initial + part_initial)

        for existing_full in final_full:
            for part_full_item in part_result["full"]:
                new_full.append(existing_full + part_full_item)

        final_initials = new_initials
        final_full = new_full

        # Strictly control total combinations
        if len(final_initials) > 3:
            final_initials = final_initials[:3]
            final_full = final_full[:3]

    # 4. Deduplicate and sort
    pinyin_initials = sorted(list(set([item for item in final_initials if item])))
    pinyin_full_list = sorted(list(set([item for item in final_full if item])))

    return {"pinyin_initials": pinyin_initials, "pinyin_full_list": pinyin_full_list}
