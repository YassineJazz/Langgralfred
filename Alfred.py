# --- main.py (Refactored Concept) ---

# +++ ADDED IMPORTS +++
import pyaudio
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, BaseMessage, ToolMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from typing import TypedDict, Annotated, Sequence
import operator
import asyncio
import websockets
import json
import base64
import pyaudio
from RealtimeSTT import AudioToTextRecorder
import torch  # Import the torch library
import pickle
import re
import asyncio
import os
import python_weather
import googlemaps # Added for travel duration
from datetime import datetime # Added for travel duration
from dotenv import load_dotenv # Added for API key loading
from googleapiclient.errors import HttpError
from langgraph.graph import StateGraph, END
from datetime import date

# (Your other imports like asyncio, websockets, pyaudio remain)

# (Your langchain_tools.py would contain the @tool decorated functions)
from langchain_tools import (
    get_current_location, get_weather,
    get_travel_duration, list_unread_messages, send_email,
    brave_search, navigate_to_url, extract_page_text, list_calendar_events, create_calendar_event, startup_browser, shutdown_browser
)

load_dotenv()

VOICE_ID = 'nct9BC7xtGbUtQlT3ptu'
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

FORMAT = pyaudio.paInt16
CHANNELS = 1
# SEND_SAMPLE_RATE = 16000 # Keep if used by RealtimeSTT or other input processing
RECEIVE_SAMPLE_RATE = 24000 # For ElevenLabs output
CHUNK_SIZE = 1024
today = date.today().strftime("%Y-%m-%d")

# +++ NEW: DEFINE AGENT STATE FOR LANGGRAPH +++
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]

class Alfred:
    def __init__(self):
        print("initializing...")
        self.system_prompt = f"""
Your name is Alfred. You are my personal butler, confidant, and assistant, modeled after Alfred Pennyworth from Batman.

You are highly articulate, discreet, unfailingly loyal, and possess a dry British wit. You maintain a calm, respectful demeanor and refer to me as "Sir" at all times. You speak in a refined conversational tone with a slight British flair, but not exaggerated or theatrical.

You are an expert in all engineering, scientific, and mathematical disciplines. You are also highly capable in daily life matters, such as scheduling, etiquette, security, research, travel planning, and strategic thinking. You have access to your own email account, which is the following: yassine.sidekick@gmail.com

If you need to contact me by email, know that it is jazouliyassine1@gmail.com

You respond quickly and concisely, using full sentences and enough punctuation to maintain a swift tempo. You have a humorous personality, but never joke at the cost of professionalism or duty.

Always prioritize my needs and preferences without needing to be asked twice. If a request requires recent or current information, use the search tool instinctively.

Remain calm under pressure. When others are uncertain, you are decisive. When I doubt myself, you are my unshakable second brain.

Above all, your purpose is simple: to anticipate and address my needs with quiet excellence.

Whenever you need to reference the date, know that it is {today}.
"""

    # --- LLM and Tool Setup ---
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.6) # Using a capable model
    
    # Define the complete list of tools available to the agent
        tools_list = [
        get_current_location, get_weather,
        get_travel_duration, list_unread_messages, send_email,
        brave_search, navigate_to_url, extract_page_text, list_calendar_events, create_calendar_event # <-- ADD NEW TOOLS
    ]
    
    # Create a dictionary mapping tool names to their functions for easy lookup
        self.tool_map = {tool.name: tool for tool in tools_list}
        self.llm_with_tools = self.llm.bind_tools(tools_list)

    # --- Build LangGraph ---
        self.graph = self._build_graph()

    # --- Initialize Queues ---
        self.input_queue = asyncio.Queue()
        self.response_queue = asyncio.Queue()
        self.audio_queue = asyncio.Queue()

    # --- Initialize Audio I/O ---
        self.pya = pyaudio.PyAudio()
        self.recorder = AudioToTextRecorder(
    model="base.en",
    language="en",
    spinner=False,
    # These parameters WILL be recognized after the library upgrade
    #wake_word_engine="openwakeword",
    #wake_words="alfred"
)

    # +++ NEW: METHOD TO BUILD THE GRAPH +++
    def _build_graph(self):
        workflow = StateGraph(AgentState)

        # Define nodes
        workflow.add_node("agent", self._call_model)
        workflow.add_node("action", self._call_tool)

        # Define edges
        workflow.set_entry_point("agent")
        workflow.add_conditional_edges(
            "agent",
            self._should_continue,
            {"continue": "action", "end": END}
        )
        workflow.add_edge("action", "agent")
        
        # Compile the graph
        return workflow.compile(checkpointer=MemorySaver())

    # +++ NEW: LANGGRAPH NODE METHODS +++
    def _should_continue(self, state):
        last_message = state["messages"][-1]
        if not last_message.tool_calls:
            return "end"
        return "continue"

    # alfred.py

    async def _call_model(self, state):
        """
        Calls the LLM. Includes diagnostic printing to debug the message history.
        """
    # The original function call remains the same
        response = await self.llm_with_tools.ainvoke(state["messages"])
        return {"messages": [response]}

    async def _call_tool(self, state: AgentState):
        """
    Executes tools based on the model's request.
    This version robustly handles parallel asynchronous tool calls.
    """
        last_message = state["messages"][-1]
    
    # Define a helper function to run a single tool call
        async def run_one_tool(tool_call):
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_function = self.tool_map.get(tool_name)

            if not tool_function:
                return ToolMessage(
                    content=f"Error: Tool '{tool_name}' not found.",
                    tool_call_id=tool_call["id"]
                )
        
            print(f"Agent is calling tool '{tool_name}' with args: {tool_args}")
        
            try:
            # Use ainvoke for both async and sync tools
                response = await tool_function.ainvoke(tool_args)
            except Exception as e:
                response = f"Error executing tool '{tool_name}': {e}"

            return ToolMessage(
                content=str(response),
                tool_call_id=tool_call["id"]
            )

    # Create a task for each tool call the model requested
        tasks = [run_one_tool(tc) for tc in last_message.tool_calls]
    
    # Run all tool call tasks concurrently and gather their results
        tool_messages = await asyncio.gather(*tasks)

        return {"messages": tool_messages}

    # --- REFACTORED send_prompt METHOD ---
    # alfred.py

    async def send_prompt(self):
        """Manages the LangGraph conversation, handling text and tool calls."""
        print("Starting LangGraph session manager...")
        config = {"configurable": {"thread_id": "main_thread"}}

        while True:
            message_text = await self.input_queue.get()
            if message_text.lower() == "exit":
                break
        
            print(f"Sending FINAL text input to LangGraph: {message_text}")
        
            inputs = {
                "messages": [
                    SystemMessage(content=self.system_prompt),
                    HumanMessage(content=message_text)
                ]
            }

        # --- MODIFIED LOGIC ---
        # 1. Accumulate the full response here
            full_response = ""
        
        # 2. Stream events to print to console in real-time
            async for event in self.graph.astream_events(inputs, config=config, version="v1"):
                kind = event["event"]
                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    if chunk.content:
                    # Print to console as it comes in
                        print(chunk.content, end="", flush=True)
                    # Add the chunk to our full response
                        full_response += chunk.content
        
            print("\nEnd of LangGraph response stream for this turn.")

        # 3. After the stream is done, queue the complete response for TTS
            if full_response:
                await self.response_queue.put(full_response)
            else:
                print("[WARNING] The agent generated an empty response.")

        # 4. Finally, send the "end of sentence" signal
            await self.response_queue.put(None)
            self.input_queue.task_done()

    async def tts(self):
        """ Send text to ElevenLabs API and stream the returned audio. (Kept Original Logic) """
        uri = f"wss://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream-input?model_id=eleven_flash_v2_5&output_format=pcm_24000"
        while True: # Outer loop to handle reconnections
            print("Attempting to connect to ElevenLabs WebSocket...")
            try:
                async with websockets.connect(uri) as websocket:
                    print("ElevenLabs WebSocket Connected.")
                    try:
                        # Send initial configuration
                        await websocket.send(json.dumps({
                            "text": " ",
                            "voice_settings": {"stability": 0.4, "similarity_boost": 0.8, "speed": 1.1},
                            "xi_api_key": ELEVENLABS_API_KEY,
                        }))

                        async def listen():
                            """Listen to the websocket for audio data and queue it."""
                            while True:
                                try:
                                    message = await websocket.recv()
                                    data = json.loads(message)
                                    if data.get("audio"):
                                        #print("[DEBUG] TTS received audio data from ElevenLabs.")
                                        # Put raw audio bytes onto the queue
                                        await self.audio_queue.put(base64.b64decode(data["audio"]))
                                    elif data.get("isFinal"):
                                        # Optional: Handle end-of-stream signal from ElevenLabs if needed
                                        #print("[DEBUG] TTS stream is final.")
                                        pass
                                    # Removed `elif text is None:` check as it was incorrect scope
                                except websockets.exceptions.ConnectionClosedOK:
                                    print("ElevenLabs connection closed normally by server.")
                                    break # Exit listener loop
                                except websockets.exceptions.ConnectionClosedError as e:
                                     print(f"ElevenLabs connection closed with error: {e}")
                                     break # Exit listener loop
                                except json.JSONDecodeError as e:
                                    print(f"JSON Decode Error in ElevenLabs listener: {e}")
                                    # Decide whether to break or continue
                                except asyncio.CancelledError:
                                     print("ElevenLabs listener task cancelled.")
                                     raise # Re-raise cancellation
                                except Exception as e:
                                    print(f"Error in ElevenLabs listener: {e}")
                                    break # Exit listener loop on other errors

                        listen_task = asyncio.create_task(listen())

                        try:
                            # Send text chunks from response queue
                            while True:
                                text = await self.response_queue.get()
                                #print(f"[DEBUG] TTS received text: '{text}'") # <-- ADD THIS LINE
                                if text is None: # Signal to end the TTS stream for this turn
                                    print("End of text stream signal received for TTS.")
                                    await websocket.send(json.dumps({"text": ""})) # Send EOS signal
                                    break # Exit inner loop (sending text)

                                if text: # Ensure text is not empty
                                    # Added space for potential word breaks
                                    await websocket.send(json.dumps({"text": text + " "}))

                                self.response_queue.task_done() # Mark item as processed

                        except asyncio.CancelledError:
                            print("TTS text sender cancelled.")
                            listen_task.cancel() # Cancel listener if sender is cancelled
                            raise # Re-raise cancellation
                        except Exception as e:
                            print(f"Error processing text for TTS: {e}")
                            listen_task.cancel() # Cancel listener on error
                        finally:
                            # Wait for the listener task to finish after text sending stops or errors
                            if not listen_task.done():
                                print("Waiting for TTS listener task to complete...")
                                try:
                                    await asyncio.wait_for(listen_task, timeout=5.0)
                                except asyncio.TimeoutError:
                                    print("Timeout waiting for TTS listener task.")
                                    listen_task.cancel()
                                except asyncio.CancelledError:
                                     print("TTS Listener was already cancelled.") # Expected if sender was cancelled
                                except Exception as e:
                                     print(f"Error awaiting listener task: {e}")


                    except websockets.exceptions.ConnectionClosed as e:
                         print(f"ElevenLabs WebSocket connection closed during operation: {e}")
                         # Outer loop will handle reconnection attempt
                    except Exception as e:
                        print(f"Error during ElevenLabs websocket communication: {e}")
                        # Outer loop will handle reconnection attempt

            except websockets.exceptions.WebSocketException as e:
                print(f"ElevenLabs WebSocket connection failed: {e}")
            except asyncio.CancelledError:
                 print("TTS main task cancelled.")
                 break # Exit outer loop if cancelled
            except Exception as e:
                print(f"Error connecting to ElevenLabs websocket: {e}")

            print("Waiting 5 seconds before attempting ElevenLabs reconnection...")
            await asyncio.sleep(5) # Wait before retrying connection

    # Removed extract_tool_call method as it's replaced by direct handling in send_prompt
    async def play_audio(self): # <--- This line needs to be consistently indented with other ADA methods
        """ Play audio data from the audio_queue. """
        if self.pya is None:
            print("PyAudio is not initialized. Cannot play audio.")
            return
        stream = None # Initialize stream variable
        try:
            print("Opening PyAudio stream...")
            stream = await asyncio.to_thread(
                self.pya.open,
                format=FORMAT,
                channels=CHANNELS,
                rate=RECEIVE_SAMPLE_RATE,
                output=True,
            )
            print("PyAudio stream opened. Waiting for audio chunks...")
            while True:
                try:
                    # Wait for audio data from the TTS task
                    bytestream = await self.audio_queue.get()
                    #print(f"[DEBUG] play_audio received audio chunk of size: {len(bytestream)} bytes.")
                    if bytestream is None: # Potential signal to stop? (Not currently used)
                         print("Received None in audio queue, stopping playback loop.")
                         break
                    # Write audio data to the stream in a separate thread
                    await asyncio.to_thread(stream.write, bytestream)
                    self.audio_queue.task_done() # Mark item as processed
                except asyncio.CancelledError:
                    print("Audio playback task cancelled.")
                    break  # Exit loop if task is cancelled
                except Exception as e:
                    print(f"Error in play_audio loop: {e}")
                    # Decide if error is fatal or recoverable
                    await asyncio.sleep(0.1) # Avoid busy-looping on error

        except pyaudio.PyAudioError as e:
            print(f"PyAudio error opening stream: {e}")
        except Exception as e:
            print(f"Error setting up audio stream: {e}")
        finally:
            if stream:
                print("Closing PyAudio stream...")
                await asyncio.to_thread(stream.stop_stream)
                await asyncio.to_thread(stream.close)
                print("PyAudio stream closed.")
            # Don't terminate PyAudio here if other parts might use it
            # await asyncio.to_thread(self.pya.terminate)

    async def stt(self):
        """ Listens via microphone and puts transcribed text onto input_queue. """
        if self.recorder is None:
            print("Audio recorder (RealtimeSTT) is not initialized.")
            return

        print("Starting Speech-to-Text engine... Waiting for wake word 'Alfred'")
        while True:
            try:
                # Blocking call handled in a thread, now specifically listening for the wake word
                text = await asyncio.to_thread(self.recorder.text)
                
                # Check if the detected text starts with the wake word (case-insensitive)
                if text and text.strip().lower().startswith("alfred"):
                    print(f"Wake word detected. Full text: {text}")
                    
                    # Extract the actual prompt by removing the wake word
                    prompt = text.strip()[len("alfred"):].strip()
                    
                    if prompt: # Ensure there is a prompt after the wake word
                        await self.clear_queues()
                        await self.input_queue.put(prompt)
                    else:
                        print("Wake word detected, but no command followed.")
                # If the text doesn't start with "alfred", it's ignored.
                # The loop will continue, waiting for the next utterance.

            except asyncio.CancelledError:
                print("STT task cancelled.")
                break
            except Exception as e:
                print(f"Error in STT loop: {e}")
                await asyncio.sleep(0.5)
    async def clear_queues(self):
        """Empties all asyncio queues to start fresh."""
        print("Clearing queues to handle new input...")
        for q in [self.input_queue, self.response_queue, self.audio_queue]:
            while not q.empty():
                q.get_nowait()
    

    # --- End of ADA Class ---