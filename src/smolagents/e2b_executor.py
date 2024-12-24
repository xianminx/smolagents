#!/usr/bin/env python
# coding=utf-8

# Copyright 2024 The HuggingFace Inc. team. All rights reserved.
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
from dotenv import load_dotenv
import textwrap
import base64
from io import BytesIO
from PIL import Image

from e2b_code_interpreter import Sandbox
from typing import List, Tuple, Any
from .tool_validation import validate_tool_attributes
from .utils import instance_to_source, BASE_BUILTIN_MODULES
from .tools import Tool

load_dotenv()


class E2BExecutor:
    def __init__(self, additional_imports: List[str], tools: List[Tool]):
        self.custom_tools = {}
        self.sbx = Sandbox()  # "qywp2ctmu2q7jzprcf4j")
        # TODO: validate installing agents package or not
        # print("Installing agents package on remote executor...")
        # self.sbx.commands.run(
        #     "pip install git+https://github.com/huggingface/agents.git",
        #     timeout=300
        # )
        # print("Installation of agents package finished.")
        if len(additional_imports) > 0:
            execution = self.sbx.commands.run(
                "pip install " + " ".join(additional_imports)
            )
            if execution.error:
                raise Exception(f"Error installing dependencies: {execution.error}")
            else:
                print("Installation succeeded!")

        tool_codes = []
        for tool in tools:
            validate_tool_attributes(tool.__class__, check_imports=False)
            tool_code = instance_to_source(tool, base_cls=Tool)
            tool_code = tool_code.replace("from smolagents.tools import Tool", "")
            tool_code += f"\n{tool.name} = {tool.__class__.__name__}()\n"
            tool_codes.append(tool_code)

        tool_definition_code = "\n".join(
            [f"import {module}" for module in BASE_BUILTIN_MODULES]
        )
        tool_definition_code += textwrap.dedent("""
        class Tool:
            def __call__(self, *args, **kwargs):
                return self.forward(*args, **kwargs)

            def forward(self, *args, **kwargs):
                pass # to be implemented in child class
        """)
        tool_definition_code += "\n\n".join(tool_codes)

        tool_definition_execution = self.run_code_raise_errors(tool_definition_code)
        print(tool_definition_execution.logs)

    def run_code_raise_errors(self, code: str):
        execution = self.sbx.run_code(
            code,
        )
        if execution.error:
            logs = "Executing code yielded an error:"
            logs += execution.error.name
            logs += execution.error.value
            logs += execution.error.traceback
            raise ValueError(logs)
        return execution

    def __call__(self, code_action: str) -> Tuple[Any, Any]:
        execution = self.run_code_raise_errors(code_action)
        execution_logs = "\n".join([str(log) for log in execution.logs.stdout])
        if not execution.results:
            return None, execution_logs
        else:
            for result in execution.results:
                if result.is_main_result:
                    for attribute_name in ["jpeg", "png"]:
                        if getattr(result, attribute_name) is not None:
                            image_output = getattr(result, attribute_name)
                            decoded_bytes = base64.b64decode(
                                image_output.encode("utf-8")
                            )
                            return Image.open(BytesIO(decoded_bytes)), execution_logs
                    for attribute_name in [
                        "chart",
                        "data",
                        "html",
                        "javascript",
                        "json",
                        "latex",
                        "markdown",
                        "pdf",
                        "svg",
                        "text",
                    ]:
                        if getattr(result, attribute_name) is not None:
                            return getattr(result, attribute_name), execution_logs
            raise ValueError("No main result returned by executor!")


__all__ = ["E2BExecutor"]
