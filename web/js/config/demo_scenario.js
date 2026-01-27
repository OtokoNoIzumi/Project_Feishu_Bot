/**
 * Demo Scenario Data (Mock)
 * Based on real user data snapshots.
 */
const DemoScenario = {
    dialogueId: 'dialogue_20260127_4f3ccb74',

    // Virtual User Profile
    userProfile: {
        "gender": "female",
        "age": 30,
        "birth_date": "1996-01-24",
        "activity_level": "sedentary",
        "timezone": "Asia/Shanghai",
        "height_cm": 168,
        "current_weight_kg": 69.6,
        "diet": {
            "energy_unit": "kJ",
            "goal": "fat_loss",
            "daily_energy_kj_target": 6456,
            "protein_g_target": 118,
            "fat_g_target": 43,
            "carbs_g_target": 171,
            "fiber_g_target": 30,
            "sodium_mg_target": 2000
        },
        "keep": {
            "weight_kg_target": 60.0,
            "body_fat_pct_target": 23.0,
            "dimensions_target": {
                "waist": 75.0,
                "bust": 94.0,
                "hip_circ": 95.0,
                "thigh": 52.0,
                "calf": 35.0,
                "arm": 24.0
            }
        },
        "user_info": "重点关注腰臀比优化。接受较长周期的科学减脂，重点在于通过力量训练强化臀腿线条以抵消减脂带来的围度缩小。",
        "estimated_months": 10,
        "registered_at": new Date().toISOString(),
        "nid": 1,
        "subscriptions": {
            "basic": new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString()
        },
        "whitelist_features": [
            "advanced_analysis",
            "detail_dimension"
        ]
    },

    dialogue: {
        id: 'dialogue_20260127_4f3ccb74',
        title: '体验演示',
        created_at: '2025-11-02T08:00:00.000Z',
        updated_at: '2025-11-02T20:13:43.138371',
    },

    // Card Details
    cards: {
        // Card 1: Keep Record
        'card_20260127_78c8e556': {
            "id": "card_20260127_78c8e556",
            "dialogue_id": "dialogue_20260127_4f3ccb74",
            "user_id": "placeholder",
            "mode": "keep",
            "title": "19:59 Keep记录 1项",
            "user_title": null,
            "source_user_note": "",
            "image_uris": [
                "assets/demo/keep_longscreenshot.png"
            ],
            "image_hashes": [
                "16d450a86cb8926711ac3e0e8d9316a5609b3dc26c8a3a809812a15f305dc21c"
            ],
            "versions": [
                {
                    "created_at": "2025-11-02T11:59:34.884Z",
                    "user_note": "",
                    "raw_result": {
                        "scale_events": [
                            {
                                "measured_at_local": "2025-11-02 09:38",
                                "weight_kg": 69.6,
                                "body_fat_pct": 18.9,
                                "bmi": 22.2,
                                "bmr_kcal_per_day": 1473,
                                "muscle_kg": 53.7,
                                "visceral_fat_level": 9,
                                "subcutaneous_fat_pct": 12.6,
                                "protein_pct": 17.1,
                                "skeletal_muscle_pct": 45.4,
                                "fat_free_mass_kg": 56.4,
                                "water_pct": 55.5,
                                "body_score": 82,
                                "body_age_years": 35
                            }
                        ],
                        "sleep_events": [],
                        "body_measure_events": [],
                        "occurred_at": "",
                        "image_hashes": [
                            "16d450a86cb8926711ac3e0e8d9316a5609b3dc26c8a3a809812a15f305dc21c"
                        ],
                        "image_count": 1
                    },
                    "advice": null,
                    "adviceError": null
                }
            ],
            "current_version": 1,
            "status": "draft",
            "saved_record_id": null,
            "created_at": "2025-11-02T11:59:18.945000Z",
            "updated_at": "2025-11-02T19:59:34.892936",
            "is_demo": false
        },

        // Card 2: Diet (Breakfast, Text Only)
        'card_20260127_56a7bf50': {
            "id": "card_20260127_56a7bf50",
            "dialogue_id": "dialogue_20260127_4f3ccb74",
            "user_id": "placeholder",
            "mode": "diet",
            "title": "19:46 早餐 265kJ",
            "user_title": null,
            "source_user_note": "明天早餐 382.4g脱脂奶 34钢切燕麦",
            "image_uris": [],
            "image_hashes": [],
            "versions": [
                {
                    "created_at": "2025-11-02T11:45:51.714Z",
                    "user_note": "明天早餐 382.4g脱脂奶 34钢切燕麦",
                    "raw_result": {
                        "meal_summary": {
                            "total_energy_kj": 1107.4211,
                            "net_weight_g": 416.4,
                            "advice": "脱脂奶搭配钢切燕麦是极佳的早餐选择，富含优质蛋白和慢消化碳水，能提供持久的饱腹感。建议可以加入少量新鲜浆果或坚果以增加微量元素摄入。",
                            "diet_time": "breakfast"
                        },
                        "captured_labels": [],
                        "dishes": [
                            {
                                "standard_name": "脱脂牛奶",
                                "ingredients": [
                                    {
                                        "name_zh": "荷高脱脂纯牛奶",
                                        "weight_g": 382.4,
                                        "weight_method": "subtraction_precise",
                                        "data_source": "label_ocr",
                                        "energy_kj": 556.6394,
                                        "macros": {
                                            "protein_g": 14.2,
                                            "fat_g": 0,
                                            "carbs_g": 19.06,
                                            "sodium_mg": 164.47,
                                            "fiber_g": 0
                                        }
                                    }
                                ]
                            },
                            {
                                "standard_name": "钢切燕麦",
                                "ingredients": [
                                    {
                                        "name_zh": "阿巴香钢切燕麦",
                                        "weight_g": 34,
                                        "weight_method": "subtraction_precise",
                                        "data_source": "label_ocr",
                                        "energy_kj": 550.7818,
                                        "macros": {
                                            "protein_g": 4.01,
                                            "fat_g": 3.64,
                                            "carbs_g": 20.71,
                                            "sodium_mg": 0,
                                            "fiber_g": 3.74
                                        }
                                    }
                                ]
                            }
                        ],
                        "user_note_process": "用户指定了明天早餐的摄入量：382.4g脱脂奶和34g钢切燕麦。根据已知产品库，匹配到“荷高脱脂纯牛奶”和“阿巴香钢切燕麦”。脱脂奶根据1.023g/ml的密度将重量转换为体积（约373.8ml）后计算营养成分；燕麦直接按34g重量计算。",
                        "occurred_at": "2025-11-02 08:00:00",
                        "image_hashes": [],
                        "image_count": 0,
                        "context": {
                            "user_target": {
                                "goal": "fat_loss",
                                "daily_energy_kj_target": 6456,
                                "protein_g_target": 118,
                                "fat_g_target": 43,
                                "carbs_g_target": 171,
                                "fiber_g_target": 30,
                                "sodium_mg_target": 2000
                            },
                            "today_so_far": {
                                "consumed_energy_kj": 0,
                                "consumed_protein_g": 0,
                                "consumed_fat_g": 0,
                                "consumed_carbs_g": 0,
                                "consumed_sodium_mg": 0,
                                "consumed_fiber_g": 0,
                                "activity_burn_kj": 0
                            },
                            "user_bio": [
                                "喜欢吃马蹄",
                                "有晚餐后安排加餐的习惯",
                                "用户偏好干蒸的烹饪方式",
                                "用户接受使用蛋白粉作为蛋白质补充手段",
                                "用户在进食重油菜品时有筛选食材避开油脂的意识",
                                "用户接受即食鸡胸肉作为蛋白质补充手段",
                                "用户有在晚餐或加餐时摄入水果（如蓝莓）的意愿"
                            ],
                            "meta": {
                                "source": "user_data",
                                "history_range": "2025-10-30 to 2025-11-02"
                            }
                        }
                    },
                    "advice": "这次早餐吃得很利落，钢切燕麦配上脱脂奶是标准的减脂优选，既保证了低GI碳水的稳步供应，又把脂肪摄入控制在了极低的水平。\n\n目前全天的营养进度才刚开始，接下来的几餐建议重点关注**蛋白质**和**膳食纤维**的补充：\n\n1.  **午餐建议（补足蛋白与纤维）：**\n    全天还有约100g的蛋白质缺口，建议午餐直接安排35-40g蛋白质。可以准备一份**马蹄蒸肉饼**或者是**干蒸鸡胸肉**（约150g-200g肉量），口感清脆又不油腻。同时，为了达成30g的纤维目标，中午至少要吃够300g的干蒸时蔬（比如菜心或西蓝花）。\n\n2.  **后续饮食策略：**\n    *   **晚餐：** 继续保持干蒸或少油炒的烹饪方式，食材上可以选些瘦肉或虾仁，避开重油的菜底，蛋白质目标依然定在30-35g。\n    *   **晚间加餐：** 考虑到你有晚间加餐的习惯，可以留出一点碳水份额给**蓝莓**。如果睡前发现全天蛋白质还没凑够，可以用**蛋白粉**灵活补位。\n\n**今日后续目标量化参考：**\n*   **蛋白质：** 还需约 100g（建议分布在午餐、晚餐及加餐）\n*   **膳食纤维：** 还需约 26g（需要大量的绿叶蔬菜支持）\n*   **脂肪：** 剩余额度约 39g（空间充足，但建议优先选不饱和脂肪来源）\n\n这样的早餐开局非常扎实，保持这个节奏，全天达标没问题！",
                    "adviceError": null
                }
            ],
            "current_version": 1,
            "status": "saved",
            "saved_record_id": "c8ca39e5dbf1",
            "created_at": "2025-11-02T11:45:33.482000Z",
            "updated_at": "2025-11-02T19:46:39.631557",
            "is_demo": false
        },

        // Card 3: Diet (Lunch, Multi-Image, Two Versions)
        'card_20260127_dfe803ab': {
            "id": "card_20260127_dfe803ab",
            "dialogue_id": "dialogue_20260127_4f3ccb74",
            "user_id": "placeholder",
            "mode": "diet",
            "title": "20:13 午餐 188kJ",
            "user_title": null,
            "source_user_note": "",
            "image_uris": [
                "assets/demo/diet_1.png",
                "assets/demo/diet_2.png",
                "assets/demo/diet_3.png",
                "assets/demo/diet_4.png"
            ],
            "image_hashes": [
                "04f795064aa36236419bd6aadeee991a18e198a8593d58c18e17350c5719b15c",
                "3ac15274b4e9d0ff56780e5986e51fba8c5380369dfc46e16e09c6e05b29fbaa",
                "1a6b9806c51968d1bf475f61853915fe478189e7ad7d21d6adbcc2d118c7b2ef",
                "f6b0b2ad4b6f1a98a23e258349af7efb133d9c8e3a0a9d0dcaa151b86290f5c0"
            ],
            "versions": [
                {
                    "created_at": "2025-11-02T12:07:15.813Z",
                    "user_note": "",
                    "raw_result": {
                        "meal_summary": {
                            "total_energy_kj": 808.0141,
                            "net_weight_g": 212,
                            "advice": "本次餐食蛋白质来源丰富（烤鸡胸肉与炒虾），搭配了芹菜和辣椒等蔬菜。建议注意炒制过程中的油脂摄入，整体营养配比较为均衡。",
                            "diet_time": "breakfast"
                        },
                        "captured_labels": [
                            {
                                "product_name": "低脂嫩烤鸡胸肉",
                                "brand": "薄荷生活",
                                "variant": "奥尔良风味",
                                "serving_size": "100g",
                                "energy_kj_per_serving": 481,
                                "protein_g_per_serving": 23.6,
                                "fat_g_per_serving": 1.6,
                                "carbs_g_per_serving": 1.2,
                                "sodium_mg_per_serving": 598,
                                "fiber_g_per_serving": 0,
                                "custom_note": ""
                            }
                        ],
                        "dishes": [
                            {
                                "standard_name": "奥尔良风味烤鸡胸肉",
                                "ingredients": [
                                    {
                                        "name_zh": "薄荷生活低脂嫩烤鸡胸肉",
                                        "weight_g": 49.8,
                                        "weight_method": "subtraction_precise",
                                        "data_source": "label_ocr",
                                        "energy_kj": 236.8144,
                                        "macros": {
                                            "protein_g": 11.75,
                                            "fat_g": 0.8,
                                            "carbs_g": 0.6,
                                            "sodium_mg": 297.8,
                                            "fiber_g": 0
                                        }
                                    }
                                ]
                            },
                            {
                                "standard_name": "芹菜辣椒炒虾",
                                "ingredients": [
                                    {
                                        "name_zh": "虾",
                                        "weight_g": 121.9,
                                        "weight_method": "subtraction_precise",
                                        "data_source": "generic_estimate",
                                        "energy_kj": 476.9342,
                                        "macros": {
                                            "protein_g": 24.38,
                                            "fat_g": 1.83,
                                            "carbs_g": 0,
                                            "sodium_mg": 365.7,
                                            "fiber_g": 0
                                        }
                                    },
                                    {
                                        "name_zh": "芹菜辣椒配菜",
                                        "weight_g": 40.3,
                                        "weight_method": "subtraction_precise",
                                        "data_source": "generic_estimate",
                                        "energy_kj": 94.2655,
                                        "macros": {
                                            "protein_g": 0.4,
                                            "fat_g": 1.61,
                                            "carbs_g": 1.61,
                                            "sodium_mg": 161.2,
                                            "fiber_g": 0.81
                                        }
                                    }
                                ]
                            }
                        ],
                        "user_note_process": "通过图片1识别到包装鸡胸肉净重为49.8g。通过图片2、3、4的称重序列（301.1g -> 179.2g -> 138.9g）计算得出：食入虾的重量约为121.9g（301.1-179.2），食入配菜及调料重量约为40.3g（179.2-138.9）。鸡胸肉数据直接复用用户产品库中的薄荷生活品牌数据。",
                        "extra_image_summary": "炒虾中含有大量切段的红辣椒、青辣椒以及洋葱块，碗底有明显的油渍和少量汤汁，属于典型的中式油炒烹饪方式。",
                        "image_hashes": [
                            "04f795064aa36236419bd6aadeee991a18e198a8593d58c18e17350c5719b15c",
                            "3ac15274b4e9d0ff56780e5986e51fba8c5380369dfc46e16e09c6e05b29fbaa",
                            "1a6b9806c51968d1bf475f61853915fe478189e7ad7d21d6adbcc2d118c7b2ef",
                            "f6b0b2ad4b6f1a98a23e258349af7efb133d9c8e3a0a9d0dcaa151b86290f5c0"
                        ],
                        "image_count": 4,
                        "context": {
                            "user_target": {
                                "goal": "fat_loss",
                                "daily_energy_kj_target": 6456,
                                "protein_g_target": 118,
                                "fat_g_target": 43,
                                "carbs_g_target": 171,
                                "fiber_g_target": 30,
                                "sodium_mg_target": 2000
                            },
                            "today_so_far": {
                                "consumed_energy_kj": 1107.4,
                                "consumed_protein_g": 18.21,
                                "consumed_fat_g": 3.64,
                                "consumed_carbs_g": 39.77,
                                "consumed_sodium_mg": 164.47,
                                "consumed_fiber_g": 3.74,
                                "activity_burn_kj": 0
                            },
                            "user_bio": [
                                "喜欢吃马蹄",
                                "有晚餐后安排加餐的习惯",
                                "用户偏好干蒸的烹饪方式",
                                "用户接受使用蛋白粉作为蛋白质补充手段",
                                "用户在进食重油菜品时有筛选食材避开油脂的意识",
                                "用户接受即食鸡胸肉作为蛋白质补充手段",
                                "用户有在晚餐或加餐时摄入水果（如蓝莓）的意愿"
                            ],
                            "meta": {
                                "source": "user_data",
                                "history_range": "2025-10-30 to 2025-11-02"
                            }
                        }
                    },
                    "advice": "这顿补了不少优质蛋白，虾和鸡胸肉加起来提供了超过 35g 的蛋白质，这对你减脂期的肌肉保留非常给力。虽然炒虾里辣椒和洋葱带来的油水看起来稍重，不过你在吃的时候注意避开碗底的油渍，这点做得很好，把脂肪摄入压得很低。\n\n既然你晚点还有加餐的习惯，建议接下来的安排走极简清淡路线：\n\n1.  **补足纤维：** 今天的膳食纤维才约 4g。等会儿可以准备一小碗**马蹄**或者抓一小把**蓝莓**。马蹄清脆爽口，蓝莓则能提供不错的抗氧化支持，最重要的是它们能在不增加额外脂肪负担的前提下，帮你把纤维缺口补上。\n2.  **注意水分：** 钠含量稍微高了一点，晚点记得多喝些水，帮助身体把多余的钠排出去，也能预防第二天早上出现水肿。\n\n总的来说，这顿蛋白质质量很高，剩下的时间交给清爽的蔬果就好。",
                    "adviceError": null
                },
                {
                    "created_at": "2025-11-02T12:13:24.317Z",
                    "user_note": "先吃虾后吃的洋葱，其他配菜没吃",
                    "raw_result": {
                        "meal_summary": {
                            "total_energy_kj": 785.3368,
                            "net_weight_g": 212,
                            "advice": "这顿午餐蛋白质来源非常丰富（鸡胸肉和虾），且搭配了洋葱和辣椒等蔬菜，整体营养密度高。建议增加一份全谷物主食（如糙米或燕麦）以补充碳水化合物，提供更持久的能量供应。",
                            "diet_time": "lunch"
                        },
                        "captured_labels": [
                            {
                                "product_name": "低脂嫩烤鸡胸肉",
                                "brand": "薄荷生活",
                                "variant": "奥尔良风味",
                                "serving_size": "100g",
                                "energy_kj_per_serving": 481,
                                "protein_g_per_serving": 23.6,
                                "fat_g_per_serving": 1.6,
                                "carbs_g_per_serving": 1.2,
                                "sodium_mg_per_serving": 598,
                                "fiber_g_per_serving": 0,
                                "custom_note": ""
                            }
                        ],
                        "dishes": [
                            {
                                "standard_name": "嫩烤鸡胸肉",
                                "ingredients": [
                                    {
                                        "name_zh": "鸡胸肉",
                                        "weight_g": 49.8,
                                        "weight_method": "subtraction_precise",
                                        "data_source": "label_ocr",
                                        "energy_kj": 236.8144,
                                        "macros": {
                                            "protein_g": 11.75,
                                            "fat_g": 0.8,
                                            "carbs_g": 0.6,
                                            "sodium_mg": 297.8,
                                            "fiber_g": 0
                                        }
                                    }
                                ]
                            },
                            {
                                "standard_name": "洋葱炒虾",
                                "ingredients": [
                                    {
                                        "name_zh": "虾",
                                        "weight_g": 121.9,
                                        "weight_method": "subtraction_precise",
                                        "data_source": "generic_estimate",
                                        "energy_kj": 476.8923,
                                        "macros": {
                                            "protein_g": 25.48,
                                            "fat_g": 1.34,
                                            "carbs_g": 0,
                                            "sodium_mg": 135.31,
                                            "fiber_g": 0
                                        }
                                    },
                                    {
                                        "name_zh": "洋葱",
                                        "weight_g": 40.3,
                                        "weight_method": "subtraction_precise",
                                        "data_source": "generic_estimate",
                                        "energy_kj": 71.6301,
                                        "macros": {
                                            "protein_g": 0.44,
                                            "fat_g": 0.04,
                                            "carbs_g": 3.75,
                                            "sodium_mg": 1.61,
                                            "fiber_g": 0.69
                                        }
                                    }
                                ]
                            }
                        ],
                        "user_note_process": "用户指定进食时间为午餐，并明确了先吃虾后吃洋葱的顺序。通过图片序列（301.1g -> 179.2g -> 138.9g）的减法链精确计算了虾（121.9g）和洋葱（40.3g）的重量。",
                        "extra_image_summary": "菜肴中含有大量的鲜红辣椒、青辣椒和西芹段作为配菜，整体呈现爆炒风格，碗底可见少量烹饪油脂和汤汁。",
                        "occurred_at": "2025-11-02 12:00:00",
                        "image_hashes": [
                            "04f795064aa36236419bd6aadeee991a18e198a8593d58c18e17350c5719b15c",
                            "3ac15274b4e9d0ff56780e5986e51fba8c5380369dfc46e16e09c6e05b29fbaa",
                            "1a6b9806c51968d1bf475f61853915fe478189e7ad7d21d6adbcc2d118c7b2ef",
                            "f6b0b2ad4b6f1a98a23e258349af7efb133d9c8e3a0a9d0dcaa151b86290f5c0"
                        ],
                        "image_count": 4,
                        "context": {
                            "user_target": {
                                "goal": "fat_loss",
                                "daily_energy_kj_target": 6456,
                                "protein_g_target": 118,
                                "fat_g_target": 43,
                                "carbs_g_target": 171,
                                "fiber_g_target": 30,
                                "sodium_mg_target": 2000
                            },
                            "today_so_far": {
                                "consumed_energy_kj": 1107.4,
                                "consumed_protein_g": 18.21,
                                "consumed_fat_g": 3.64,
                                "consumed_carbs_g": 39.77,
                                "consumed_sodium_mg": 164.47,
                                "consumed_fiber_g": 3.74,
                                "activity_burn_kj": 0
                            },
                            "user_bio": [
                                "喜欢吃马蹄",
                                "有晚餐后安排加餐的习惯",
                                "用户偏好干蒸的烹饪方式",
                                "用户接受使用蛋白粉作为蛋白质补充手段",
                                "用户在进食重油菜品时有筛选食材避开油脂的意识",
                                "用户接受即食鸡胸肉作为蛋白质补充手段",
                                "用户有在晚餐或加餐时摄入水果（如蓝莓）的意愿"
                            ],
                            "meta": {
                                "source": "user_data",
                                "history_range": "2025-10-30 to 2025-11-02"
                            }
                        }
                    },
                    "advice": "今天的午餐蛋白质给得很足，37.7克的优质蛋白对减脂期的肌肉保护非常到位。而且你挑食材避开油脂的习惯很好，这顿饭整体非常清爽。不过，这餐的碳水和膳食纤维几乎可以忽略不计，下午可能会觉得饿得比较快。\n\n算上早餐，你目前还差大约 62克蛋白质和 127克碳水，纤维缺口也比较大。\n\n**接下来的补救与互补建议：**\n\n1.  **晚餐：主攻“纤维与容积”**\n    *   现在的纤维摄入量还不到 5克，距离 30克的目标差得挺多。晚餐建议来一大盘**干蒸的绿叶菜**（比如 250克左右的生菜、菜心或芥兰），这种烹饪方式能最大程度保留营养且不额外增加油脂。\n    *   主食补足：建议摄入 60-80克左右的**钢切燕麦**或等量粗粮，把碳水水位拉上来。\n\n2.  **晚间加餐：精准补位**\n    *   你的蛋白质还差 30克左右，刚好可以在晚间加餐通过**一杯蛋白粉**来快速补充。\n    *   口感调节：可以在加餐里加入**一小碗蓝莓和几颗切碎的马蹄**。马蹄的清脆和蓝莓的酸甜能让口感更有层次，同时也补上了一部分微量元素和剩余的纤维额度。\n\n**解答你的疑问：**\n关于你提到的“先吃虾后吃洋葱”，这种进食顺序其实对血糖控制很有利。先摄入蛋白质再摄入蔬菜和碳水，可以减缓血糖上升速度，对减脂非常友好。\n\n目前你的脂肪额度还剩下 30多克，空间非常充裕，晚餐烹饪时即便有一点正常用油也不必担心，保持现在的状态就好！",
                    "adviceError": null
                }
            ],
            "current_version": 2,
            "status": "draft",
            "saved_record_id": null,
            "created_at": "2025-11-02T12:06:48.818000Z",
            "updated_at": "2025-11-02T20:13:43.138371",
            "is_demo": false
        }
    },

    messages: [
        {
            "id": "demo_msg_001",
            "role": "user",
            "title": "Keep - 1条记录",
            "content": "",
            "timestamp": "2025-11-02T09:00:00.000Z",
            "attachments": [
                "assets/demo/keep_longscreenshot.jpg"
            ],
            "linked_card_id": "card_20260127_78c8e556"
        },
        {
            "id": "demo_msg_002",
            "role": "user",
            "title": "早餐 1107 kJ",
            "content": "早餐 382.4g脱脂奶 34钢切燕麦",
            "timestamp": "2025-11-02T09:01:00.000Z",
            "linked_card_id": "card_20260127_56a7bf50"
        },
        {
            "id": "demo_msg_003",
            "role": "user",
            "content": "午餐吃点啥好？",
            "timestamp": "2025-11-02T09:02:00.000Z"
        },
        {
            "id": "demo_msg_004",
            "role": "assistant",
            "content": "即食鸡胸肉简直是现在的“满分答案”！我刚帮你算了下，蛋白质缺口补得很稳，晚点配点蔬菜就更均衡了。",
            "timestamp": "2025-11-02T09:03:00.000Z"
        },
        {
            "id": "demo_msg_005",
            "role": "user",
            "title": "午餐 785 kJ",
            "content": "先吃虾后吃的洋葱，其他配菜没吃",
            "timestamp": "2025-11-02T09:04:00.000Z",
            "attachments": [
                "assets/demo/diet_1.jpg",
                "assets/demo/diet_2.jpg",
                "assets/demo/diet_3.jpg",
                "assets/demo/diet_4.jpg"
            ],
            "linked_card_id": "card_20260127_dfe803ab"
        }
    ]
};
