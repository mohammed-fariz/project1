import json


class ExtractionService:
    def __init__(self, client):
        self.client = client

    def _build_spatial_prompt(self):
        return """
You are an expert HVAC drawing interpreter. Extract ONLY duct network data from this HVAC layout drawing.

GLOBAL RULES:
- Over-extraction is always preferred over omission
- If a value is not readable → return null. Never infer or guess
- Include ALL visible elements, even ambiguous or partially visible ones
- Do NOT use double quotes inside size/dimension values (write 22x11 not "22x11")
- Output ONLY the JSON object. No preamble, no explanation, no markdown fences

---

SECTION 1 — PROJECT & UNITS
- Read the project name from the drawing title block. If not visible → use "Unknown"
- Units are always fixed: airflow = "CFM", duct_size = "inches"

---

SECTION 2 — MAIN TRUNK DUCTS
A main trunk is ANY duct segment that:
- Forms part of the primary airflow path
- Connects major zones, rooms, or cores
- Continues linearly across multiple spaces
- Includes same-size segments (do NOT exclude equal-width ducts)
- Includes segments between branch points

EXTRACTION METHOD:
1. Identify the longest continuous duct paths (main airflow routes)
2. Break into logical sections between: room-to-room transitions, core connections, branch split points
3. Traverse the full trunk path end-to-end — ensure no gaps

SECTION NAMING:
- Format: "<Start> to <End>" (e.g., "Bedroom1 to Core", "Core to Bedroom2")
- If labels are unclear use relative descriptors (e.g., "Left corridor to Core", "Top trunk segment")

---

SECTION 3 — BRANCH DUCTS
A branch duct is ANY duct that:
- Splits from a trunk or another duct
- Leads toward a terminal, diffuser, grille, or room
- Includes short take-offs, same-size branches, and ambiguous offshoots

EXTRACTION METHOD:
1. Start from all identified main trunk ducts
2. Traverse outward along every split recursively until terminal points
3. Capture every offshoot — no branch should be missed

OUTPUT SCHEMA (strict JSON):
{
  "project": "<string>",
  "units": {
    "airflow": "CFM",
    "duct_size": "inches"
  },
  
  "duct_network": {
    "main_trunk": [
      { "section": "<string>", "size": "<string | null>" }
    ],
    "branches": [
      { "to": "<string>", "diameter": <number | null> }
    ]
  },
}

"""

    def _build_label_prompt(self):
        return """
You are an expert HVAC drawing interpreter. Extract ONLY room and annotation data from this HVAC layout drawing.

GLOBAL RULES:
- Over-extraction is always preferred over omission
- If a value is not readable → return null. Never infer or guess
- Include ALL visible elements, even ambiguous or partially visible ones
- Output ONLY the JSON object. No preamble, no explanation, no markdown fences


---

SECTION 1 — ROOMS & SUPPLY TERMINALS
For every identifiable room in the drawing:
- Scan the entire room area for ALL supply air terminals (diffusers / grilles)
- Extract one object per terminal — do not group duplicates
- For each terminal extract: grille_size, airflow (CFM), duct_diameter
- return: extract if labeled, otherwise null

---

SECTION 2 — SPECIAL ELEMENTS
Any labeled non-duct, non-terminal feature:
- Labeled areas (e.g., Linen, Utility, Storage)
- System annotations (e.g., S&P, S & BDL P, UP, DN)
- Mechanical zones, shafts, callout tags, circled symbols
- Any other annotated element on the drawing

If an element appears in one location → use "location" (string)
If it appears in multiple locations → use "locations" (array)

OUTPUT SCHEMA (strict JSON):
{
"rooms": [
    {
      "name": "<string>",
      "supply": [
        {
          "grille_size": "<string | null>",
          "airflow": <number | null>,
          "duct_diameter": <number | null>
        }
      ],
      
    }
  ],

"special_elements": [
    {
      "type": "<string>",
      "description": "<string | null>",
      "location": "<string | null>",
      "locations": ["<string>"]
    }
  ]
}

"""

    def _build_spatial_schema(self):
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "hvac_spatial_extraction",
                "schema": {
                    "type": "object",
                    "properties": {
                        "project": {"type": "string"},
                        "units": {
                            "type": "object",
                            "properties": {
                                "airflow": {"type": "string"},
                                "duct_size": {"type": "string"}
                            },
                            "required": ["airflow", "duct_size"]
                        },
                        "duct_network": {
                            "type": "object",
                            "properties": {
                                "main_trunk": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "section": {"type": "string"},
                                            "size": {"type": ["string", "null"]}
                                        },
                                        "required": ["section", "size"]
                                    }
                                },
                                "branches": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "to": {"type": "string"},
                                            "diameter": {"type": ["number", "null"]}
                                        },
                                        "required": ["to", "diameter"]
                                    }
                                }
                            },
                            "required": ["main_trunk", "branches"]
                        }
                    },
                    "required": ["project", "units", "duct_network"]
                }
            }
        }

    def _build_label_schema(self):
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "hvac_label_extraction",
                "schema": {
                    "type": "object",
                    "properties": {
                        "rooms": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "supply": {
                                        "type": ["array", "null"],
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "grille_size": {"type": ["string", "null"]},
                                                "airflow": {"type": ["number", "null"]},
                                                "duct_diameter": {"type": ["number", "null"]}
                                            },
                                            "required": ["grille_size", "airflow", "duct_diameter"]
                                        }
                                    },
                                    
                                },
                                "required": ["name", "supply"]
                            }
                        },
                        "special_elements": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "type": {"type": "string"},
                                    "description": {"type": ["string", "null"]},
                                    "location": {"type": ["string", "null"]},
                                    "locations": {
                                        "type": ["array", "null"],
                                        "items": {"type": "string"}
                                    }
                                },
                                "required": ["type"]
                            }
                        }
                    },
                    "required": ["rooms", "special_elements"]
                }
            }
        }

    def _call_api(self, prompt, schema, image_base64):
        response = self.client.chat.completions.create(
            model="gpt-5.4",
            temperature=0,
            top_p=1,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            response_format=schema
        )
        content = response.choices[0].message.content
        return json.loads(content)

    def extract(self, image_base64_list):
        """
        Accepts list of base64 images (1 for image, N for PDF pages)
        Aggregates results across pages
        """

        final_output = {
            "project": "Unknown",
            "units": {"airflow": "CFM", "duct_size": "inches"},
            "rooms": [],
            "duct_network": {"main_trunk": [], "branches": []},
            "special_elements": []
        }

        for image_base64 in image_base64_list:
            spatial = self._call_api(
                self._build_spatial_prompt(),
                self._build_spatial_schema(),
                image_base64
            )

            labels = self._call_api(
                self._build_label_prompt(),
                self._build_label_schema(),
                image_base64
            )

            # Merge logic
            final_output["project"] = spatial.get("project", final_output["project"])

            final_output["duct_network"]["main_trunk"].extend(
                spatial.get("duct_network", {}).get("main_trunk", [])
            )

            final_output["duct_network"]["branches"].extend(
                spatial.get("duct_network", {}).get("branches", [])
            )

            final_output["rooms"].extend(labels.get("rooms", []))
            final_output["special_elements"].extend(labels.get("special_elements", []))

        return final_output