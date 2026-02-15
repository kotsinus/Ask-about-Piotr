# Copyright 2026 Piotr Synak
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Purpose:
# Canonical routing taxonomy for question intent.

from __future__ import annotations

from enum import StrEnum


class RoutingCategory(StrEnum):
    hands_on_engineering = "Hands-on engineering"
    architecture_and_system_design = "Architecture and system design"
    ai_and_ml_practice = "AI and ML practice"
    leadership_and_product_strategy = "Leadership and product strategy"
    research_and_academic_credibility = "Research and academic credibility"
    career_fit_and_role_alignment = "Career fit and role alignment"
    education_and_formal_background = "Education and formal background"
    personal_interests_and_working_style = "Personal interests and working style"
