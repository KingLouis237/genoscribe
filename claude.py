"""
simple_claude_chat.py

A beginner-friendly example of how to build a simple terminal chatbot
using the Anthropic Claude API.

This script:
1. Loads your API key from an environment variable
2. Creates a client connection to Anthropic
3. Continuously asks the user for input
4. Sends the message to Claude
5. Prints Claude's response
6. Stops when the user types "exit"

Requirements:
- Install anthropic package:
    pip install anthropic

- Set your API key as an environment variable:
    On macOS/Linux:
        export ANTHROPIC_API_KEY="your_key_here"

    On Windows:
        setx ANTHROPIC_API_KEY "your_key_here"
"""

# Import the Anthropic SDK (Software Development Kit)
import anthropic

# Import the os module to access environment variables
import os


def create_client():
    """
    Creates and returns an Anthropic client object.

    The client is responsible for communicating with the Claude API.

    Returns:
        anthropic.Anthropic: A configured client instance.

    Raises:
        ValueError: If the API key is not found in environment variables.
    """

    # Retrieve API key from environment variable
    api_key = os.getenv("ANTHROPIC_API_KEY")

    # If the API key is missing, stop the program with an error
    if api_key is None:
        raise ValueError(
            "API key not found. Please set ANTHROPIC_API_KEY as an environment variable."
        )

    # Create and return the Anthropic client
    return anthropic.Anthropic(api_key=api_key)


# Global conversation list
# This list stores the entire conversation history between the user and Claude.
# Each item in the list is a dictionary with:
#   - "role": who is speaking ("user" or "assistant")
#   - "content": the text message
#
# Why this is important:
# Claude's API does NOT automatically remember previous messages.
# We must manually send the entire conversation each time.

conversation = []


def get_claude_response(client, user_input):
    """
    Sends a user message to Claude while preserving conversation memory.

    This function:
    1. Adds the user's message to the global conversation list
    2. Sends the full conversation history to Claude
    3. Receives Claude's response
    4. Adds Claude's response back into the conversation list
    5. Returns Claude's reply text

    Args:
        client (anthropic.Anthropic):
            An authenticated Anthropic client instance.

        user_input (str):
            The latest message entered by the user.

    Returns:
        str:
            Claude's text response.
    """

    # Step 1: Add the user's message to conversation history
    conversation.append({
        "role": "user",        # Indicates the speaker is the user
        "content": user_input  # The actual text typed by the user
    })

    # Step 2: Send the entire conversation to Claude
    # IMPORTANT:
    # We send the full history every time.
    # This is how Claude maintains context.
    response = client.messages.create(
        model="claude-3-haiku-20240307",  # The model being used
        max_tokens=1024,                  # Maximum tokens Claude can generate
        messages=conversation             # Full conversation history
    )

    # Step 3: Extract Claude's response text
    # Claude returns structured output.
    # response.content is a list of blocks.
    # We take the first block's text.
    assistant_text = response.content[0].text

    # Step 4: Add Claude's reply to conversation history
    conversation.append({
        "role": "assistant",       # Indicates Claude is speaking
        "content": assistant_text  # Claude's response text
    })

    # Step 5: Return Claude's reply so it can be printed
    return assistant_text



def main():
    """
    Main function that runs the chatbot loop.

    This function:
    - Creates the API client
    - Starts an infinite loop
    - Accepts user input
    - Sends input to Claude
    - Prints Claude's reply
    - Stops when the user types "exit"
    """

    # Create API client
    client = create_client()

    print("Claude Chat Started. Type 'exit' to quit.\n")

    # Infinite loop — keeps running until manually stopped
    while True:

        # Ask user for input from terminal
        user_input = input("You: ")

        # Convert input to lowercase and check if user wants to quit
        if user_input.lower() == "exit":
            print("Goodbye!")
            break  # Stops the loop

        try:
            # Get Claude's response
            reply = get_claude_response(client, user_input)

            # Print Claude's response
            print("Claude:", reply)

        except Exception as e:
            # Catch unexpected errors (e.g., network failure)
            print("An error occurred:", str(e))


# This ensures main() only runs if the script is executed directly
# (not when imported as a module)
if __name__ == "__main__":
    main()

