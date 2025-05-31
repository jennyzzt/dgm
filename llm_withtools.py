import ast
import json
import os
import re
import anthropic
import backoff
import openai
import copy

from llm import create_client, get_response_from_llm
from prompts.tooluse_prompt import get_tooluse_prompt
from tools import load_all_tools

CLAUDE_MODEL = os.getenv('CODING_AGENT_MODEL', 'anthropic/claude-3.5-sonnet')
OPENAI_MODEL = os.getenv('DEFAULT_OPENAI_MODEL', 'o3-mini-2025-01-31')

def process_tool_call(tools_dict, tool_name, tool_input):
    try:
        if tool_name in tools_dict:
            return tools_dict[tool_name]['function'](**tool_input)
        else:
            return f"Error: Tool '{tool_name}' not found"
    except Exception as e:
        return f"Error executing tool '{tool_name}': {str(e)}"

@backoff.on_exception(
    backoff.expo,
    (openai.RateLimitError, openai.APITimeoutError, anthropic.RateLimitError, anthropic.APIStatusError),
    max_time=600,
    max_value=60,
)
def get_response_withtools(
    client, model, messages, tools, tool_choice,
    logging=None, max_retry=3
):
    try:
        if 'claude' in model and not model.startswith('anthropic/'):
            # Direct Anthropic API
            response = client.messages.create(
                model=model,
                messages=messages,
                max_tokens=4096,
                tool_choice=tool_choice,
                tools=tools,
            )
        elif model.startswith('anthropic/'):
            # OpenRouter API for Anthropic models - convert messages format
            openai_messages = []
            for msg in messages:
                if isinstance(msg, dict):
                    role = msg.get('role', 'user')
                    content = msg.get('content', [])
                    if isinstance(content, list):
                        # Convert Claude format to OpenAI format
                        text_content = ""
                        for block in content:
                            if isinstance(block, dict) and block.get('type') == 'text':
                                text_content += block.get('text', '')
                            elif hasattr(block, 'type') and block.type == 'text':
                                text_content += getattr(block, 'text', '')
                        openai_messages.append({"role": role, "content": text_content})
                    else:
                        openai_messages.append({"role": role, "content": str(content)})
            
            response = client.chat.completions.create(
                model=model,
                messages=openai_messages,
                max_tokens=4096,
                tool_choice=tool_choice,
                tools=tools,
            )
        elif model.startswith('o3-') or model.startswith('openai/o3-'):
            response = client.responses.create(
                model=model,
                input=messages,
                tool_choice=tool_choice,
                tools=tools,
                parallel_tool_calls=False
            )
            response = response
        else:
            raise ValueError(f"Unsupported model: {model}")
        return response
    except Exception as e:
        logging(f"Error in get_response_withtools: {str(e)}")
        if max_retry > 0:
            return get_response_withtools(client, model, messages, tools, tool_choice, logging, max_retry - 1)

        # Hitting the context window limit
        if 'Input is too long for requested model' in str(e):
            pass

        raise  # Re-raise the exception after logging

def check_for_tool_use(response, model=''):
    """
    Checks if the response contains a tool call.
    """
    if 'claude' in model or model.startswith('anthropic/'):
        # Claude, check for stop_reason in response
        if response.stop_reason == "tool_use":
            tool_use_block = next(block for block in response.content if block.type == "tool_use")
            return {
                'tool_id': tool_use_block.id,
                'tool_name': tool_use_block.name,
                'tool_input': tool_use_block.input,
            }

    elif model.startswith('o3-') or model.startswith('openai/o3-'):
        # OpenAI, check for tool_calls in response
        for tool_call in response.output:
            if tool_call.type == "function_call":
                break

        if tool_call:
            return {
                'tool_id': tool_call.call_id,
                'tool_name': tool_call.name,
                'tool_input': json.loads(tool_call.arguments),
            }

    else:
        # Any other LLM, response is str, check for <tool_use> tag in response
        pattern = r'<tool_use>(.*?)</tool_use>'
        match = re.search(pattern, response, re.DOTALL)
        if match:
            tool_use_str = match.group(1).strip()
            try:
                tool_use_dict = ast.literal_eval(tool_use_str)
                if isinstance(tool_use_dict, dict) and 'tool_name' in tool_use_dict and 'tool_input' in tool_use_dict:
                    return tool_use_dict
            except Exception:
                pass

    # No tool use found
    return None

def convert_tool_info(tool_info, model=None):
    """
    Converts tool_info from Claude format to the given model's format.
    """
    if 'claude' in model or model.startswith('anthropic/'):
        # should have no change
        return {
            'name': tool_info['name'],
            'description': tool_info['description'],
            'input_schema': tool_info['input_schema'],
        }
    elif model.startswith('o3-') or model.startswith('openai/o3-'):
        def add_additional_properties(d):
            if isinstance(d, dict):
                if 'properties' in d:
                    d['additionalProperties'] = False
                for k, v in d.items():
                    add_additional_properties(v)
        add_additional_properties(tool_info['input_schema'])
        for p in tool_info['input_schema']['properties'].keys():
            if not p in tool_info['input_schema']['required']:
                tool_info['input_schema']['required'].append(p)
                t = copy.deepcopy(tool_info['input_schema']['properties'][p]["type"])
                if isinstance(t, str):
                    tool_info['input_schema']['properties'][p]["type"] = [t, "null"]
                elif isinstance(t, list):
                    tool_info['input_schema']['properties'][p]["type"] = t + ["null"]
                
        return {
            'type': 'function',
            'name': tool_info['name'],
            'description': tool_info['description'],
            'parameters': tool_info['input_schema'],
            "strict": True,
        }
    else:
        return tool_info

def convert_block_claude(block):
    """
    Convert a single block of content from Claude into a standard format.
    """
    if isinstance(block, dict):
        block_type = block.get('type')
        text = block.get('text')
        tool_name = block.get('name')
        tool_input = block.get('input')
        tool_result = block.get('content')
    else:
        block_type = getattr(block, 'type', None)
        text = getattr(block, 'text', None)
        tool_name = getattr(block, 'name', None)
        tool_input = getattr(block, 'input', None)
        tool_result = getattr(block, 'content', None)

    text = text or ""

    if block_type == "text":
        return {
            "type": "text",
            "text": text
        }
    elif block_type == "tool_use":
        # Convert to the manual tool calling format
        return {
            "type": "text",
            "text": f"<tool_use>\n{{'tool_name': {tool_name}, 'tool_input': {tool_input}}}\n</tool_use>"
        }
    elif block_type == "tool_result":
        return {
            "type": "text",
            "text": f"Tool Result: {tool_result}"
        }
    else:
        # Fallback if we ever encounter an unknown block type
        return {
            "type": "text",
            "text": str(block)
        }

def convert_msg_history_claude(msg_history):
    """
    Convert Claude-style message history into a generic format.
    """
    new_msg_history = []

    for msg in msg_history:
        role = msg.get('role', '')
        content_blocks = msg.get('content', [])
        new_content = []

        for block in content_blocks:
            new_content.append(convert_block_claude(block))

        new_msg_history.append({
            "role": role,
            "content": new_content
        })

    return new_msg_history

def convert_msg_history_openai(msg_history):
    """
    Convert OpenAI-style message history into a generic format.
    """
    new_msg_history = []

    for msg in msg_history:
        if isinstance(msg, dict):
            role = msg.get('role', '')
            content = msg.get('content', '')

            if role == 'tool':
                new_msg = {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Tool Result: {content}",
                        }
                    ],
                }
            else:
                new_msg = {
                    "role": role,
                    "content": content,
                }
        else:
            role = getattr(msg, 'role', None)
            content = getattr(msg, 'content', None)
            tool_calls = getattr(msg, 'tool_calls', None)

            if tool_calls:
                tool_call = tool_calls[0]
                function_name = getattr(tool_call.function, 'name', '')
                function_args = getattr(tool_call.function, 'arguments', '')
                # Convert to the manual tool calling format
                new_msg = {
                    "role": role,
                    "content": [
                        {
                            "type": "text",
                            "text": f"<tool_use>\n{{'tool_name': {function_name}, 'tool_input': {function_args}}}\n</tool_use>",
                        }
                    ],
                }
            else:
                new_msg = {
                    "role": role,
                    "content": [
                        {
                            "type": "text",
                            "text": content,
                        }
                    ],
                }

        new_msg_history.append(new_msg)

    return new_msg_history

def convert_msg_history(msg_history, model=None):
    """
    Convert message history from the model-specific format to a generic format.
    """
    if 'claude' in model or model.startswith('anthropic/'):
        return convert_msg_history_claude(msg_history)
    elif model.startswith('o3-') or model.startswith('openai/o3-'):
        return convert_msg_history_openai(msg_history)
    else:
        return msg_history

def chat_with_agent_manualtools(msg, model, msg_history=None, logging=print):
    # Construct message
    if msg_history is None:
        msg_history = []
    system_message = f'You are a coding agent.\n\n{get_tooluse_prompt()}'
    new_msg_history = msg_history

    try:
        # Load all tools
        all_tools = load_all_tools(logging=logging)
        tools_dict = {tool['info']['name']: tool for tool in all_tools}
        
        # Create client
        client, client_model = create_client(model)

        # Call API
        logging(f"Input: {msg}")
        response, new_msg_history = get_response_from_llm(
            msg=msg,
            client=client,
            model=client_model,
            system_message=system_message,
            print_debug=False,
            msg_history=new_msg_history,
        )
        logging(f"Output: {response}")

        # Tool use
        tool_use = check_for_tool_use(response, model=client_model)
        while tool_use:
            # Process tool call
            tool_name = tool_use['tool_name']
            tool_input = tool_use['tool_input']
            tool_result = process_tool_call(tools_dict, tool_name, tool_input)

            # Get tool response
            tool_msg = f'Tool Used: {tool_name}\nTool Input: {tool_input}\nTool Result: {tool_result}'
            logging(tool_msg)
            response, new_msg_history = get_response_from_llm(
                msg=tool_msg,
                client=client,
                model=client_model,
                system_message=system_message,
                print_debug=False,
                msg_history=new_msg_history,
            )
            logging(f"Output: {response}")

            # Check for next tool use
            tool_use = check_for_tool_use(response, model=client_model)

    except Exception:
        pass

    return new_msg_history

def chat_with_agent_claude(
        msg,
        model=None,
        msg_history=None,
        logging=print,
    ):
    if model is None:
        model = CLAUDE_MODEL
    # Construct message
    if msg_history is None:
        msg_history = []
    new_msg_history = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": msg,
                }
            ],
        }
    ]

    try:
        # Create client
        client, client_model = create_client(model)

        # Load all tools
        all_tools = load_all_tools(logging=logging)
        tools_dict = {tool['info']['name']: tool for tool in all_tools}
        tools = [convert_tool_info(tool['info'], model=client_model) for tool in all_tools]

        # Call API
        if client_model.startswith('anthropic/'):
            # OpenRouter uses "auto" instead of {"type": "auto"}
            tool_choice_param = "auto"
        else:
            # Direct Anthropic API uses {"type": "auto"}
            tool_choice_param = {"type": "auto"}
            
        response = get_response_withtools(
            client=client,
            model=client_model,
            messages=msg_history + new_msg_history,
            tool_choice=tool_choice_param,
            tools=tools,
            logging=logging,
        )

        # Check for tool use
        tool_use = check_for_tool_use(response, model=client_model)
        while tool_use:
            # Process tool call
            tool_name = tool_use['tool_name']
            tool_input = tool_use['tool_input']
            tool_result = process_tool_call(tools_dict, tool_name, tool_input)

            # Get tool response
            new_msg_history.append({"role": "assistant", "content": response.content})
            new_msg_history.append({
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use['tool_id'],
                        "content": tool_result,
                    }
                ],
            })
            response = get_response_withtools(
                client=client,
                model=client_model,
                messages=msg_history + new_msg_history,
                tool_choice=tool_choice_param,
                tools=tools,
                logging=logging,
            )

            # Check for next tool use
            tool_use = check_for_tool_use(response, model=client_model)

        # Get final response
        final_response = next((block.text for block in response.content if hasattr(block, "text")), None)
        new_msg_history.append({
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": final_response,
                }
            ],
        })

    except Exception:
        pass

    return new_msg_history

def chat_with_agent_openai(
        msg,
        model='o3-mini-2025-01-31',
        msg_history=None,
        logging=print,
    ):
    # Construct message
    if msg_history is None:
        msg_history = []
    new_msg_history = [
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": msg,
                }
            ],
        }
    ]
    separator = '=' * 10
    logging(f"\n{separator} User Instruction {separator}\n{msg}")
    try:
        # Create client
        client, client_model = create_client(model)

        # Load all tools
        all_tools = load_all_tools(logging=logging)
        tools_dict = {tool['info']['name']: tool for tool in all_tools}
        tools = [convert_tool_info(tool['info'], model=client_model) for tool in all_tools]

        # Call API
        response = get_response_withtools(
            client=client,
            model=client_model,
            messages=msg_history + new_msg_history,
            tool_choice="auto",
            tools=tools,
            logging=logging,
        )
        logging(f"\n{separator} Agent Response {separator}\n{response}")

        # Check for tool use
        tool_use = check_for_tool_use(response, model=client_model)
        logging(tool_use)
        while tool_use:
            # Process tool call
            tool_name = tool_use['tool_name']
            tool_input = tool_use['tool_input']
            tool_result = process_tool_call(tools_dict, tool_name, tool_input)

            logging(f"Tool Used: {tool_name}")
            logging(f"Tool Input: {tool_input}")
            logging(f"Tool Result: {tool_result}")

            # Get tool response
            for tool_call in response.output:
                if tool_call.type == "function_call":
                    break
            new_msg_history.append(tool_call)
            new_msg_history.append({
                "type": "function_call_output",
                "call_id": tool_use['tool_id'],
                "output": tool_result,
            })
            response = get_response_withtools(
                client=client,
                model=client_model,
                messages=msg_history + new_msg_history,
                tool_choice="auto",
                tools=tools,
                logging=logging,
            )

            # Check for next tool use
            tool_use = check_for_tool_use(response, model=client_model)

            logging(f"Tool Response: {response}")

        # Get final response
        new_msg_history.append(response)

    except Exception:
        pass

    return new_msg_history

def chat_with_agent(
    msg,
    model=CLAUDE_MODEL,
    msg_history=None,
    logging=print,
    convert=False,  # Convert the message history to a generic format, so that msg_history can be used across models
):
    if msg_history is None:
        msg_history = []

    if 'claude' in model or model.startswith('anthropic/'):
        # Claude models
        new_msg_history = chat_with_agent_claude(msg, model=model, msg_history=msg_history, logging=logging)
        conv_msg_history = convert_msg_history(new_msg_history, model=model)
        logging(conv_msg_history)
        if convert:
            new_msg_history = conv_msg_history
        new_msg_history = msg_history + new_msg_history

    elif model.startswith('o3-') or model.startswith('openai/o3-'):
        # OpenAI models
        new_msg_history = chat_with_agent_openai(msg, model=model, msg_history=msg_history, logging=logging)
        # Current version does not support cross-model conversion
        # new_msg_history = convert_msg_history(new_msg_history, model=model)
        new_msg_history = msg_history + new_msg_history

    else:
        # Models without in-built tool calling
        new_msg_history = chat_with_agent_manualtools(msg, model=model, msg_history=msg_history, logging=logging)
        conv_msg_history = convert_msg_history(new_msg_history, model=model)
        if convert:
            new_msg_history = conv_msg_history

    return new_msg_history


if __name__ == "__main__":
    # Test the tool calling functionality
    msg = "hello!"
    chat_with_agent(msg)
