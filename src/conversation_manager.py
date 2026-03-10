"""
ConversationManager module for maintaining conversation context and history.
"""

import uuid
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, field
from src.query_engine import Message


@dataclass
class Conversation:
    """Represents a conversation with its history."""
    id: str
    messages: List[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    max_messages: int = 10


class ConversationManager:
    """
    Manages conversation history and context for the Q&A system.
    
    Maintains conversation state in memory (designed for Streamlit session state).
    Limits conversation history to the last 10 messages to manage context window.
    """
    
    def __init__(self, max_messages: int = 10):
        """
        Initialize the ConversationManager.
        
        Args:
            max_messages: Maximum number of messages to keep in history (default: 10)
        """
        self.max_messages = max_messages
        self.conversations: Dict[str, Conversation] = {}
    
    def create_conversation(self) -> str:
        """
        Create a new conversation with a unique ID.
        
        Returns:
            Unique conversation ID (UUID)
        """
        conversation_id = str(uuid.uuid4())
        conversation = Conversation(
            id=conversation_id,
            max_messages=self.max_messages
        )
        self.conversations[conversation_id] = conversation
        return conversation_id
    
    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str
    ) -> None:
        """
        Add a message to the conversation history.
        
        Automatically limits history to the last max_messages messages.
        
        Args:
            conversation_id: ID of the conversation
            role: Message role ('user' or 'assistant')
            content: Message content
            
        Raises:
            ValueError: If conversation_id doesn't exist or role is invalid
        """
        if conversation_id not in self.conversations:
            raise ValueError(f"Conversation {conversation_id} not found")
        
        if role not in ["user", "assistant"]:
            raise ValueError(f"Invalid role: {role}. Must be 'user' or 'assistant'")
        
        conversation = self.conversations[conversation_id]
        
        # Create and add the message
        message = Message(role=role, content=content)
        conversation.messages.append(message)
        
        # Limit to last max_messages
        if len(conversation.messages) > conversation.max_messages:
            conversation.messages = conversation.messages[-conversation.max_messages:]
        
        # Update timestamp
        conversation.updated_at = datetime.now()
    
    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """
        Retrieve a conversation by ID.
        
        Args:
            conversation_id: ID of the conversation to retrieve
            
        Returns:
            Conversation object if found, None otherwise
        """
        return self.conversations.get(conversation_id)
    
    def get_messages(self, conversation_id: str) -> List[Message]:
        """
        Get all messages from a conversation.
        
        Args:
            conversation_id: ID of the conversation
            
        Returns:
            List of Message objects (empty list if conversation not found)
        """
        conversation = self.get_conversation(conversation_id)
        if conversation:
            return conversation.messages
        return []
    
    def clear_conversation(self, conversation_id: str) -> bool:
        """
        Clear all messages from a conversation (reset conversation state).
        
        Args:
            conversation_id: ID of the conversation to clear
            
        Returns:
            True if conversation was cleared, False if not found
        """
        if conversation_id not in self.conversations:
            return False
        
        conversation = self.conversations[conversation_id]
        conversation.messages = []
        conversation.updated_at = datetime.now()
        return True
    
    def delete_conversation(self, conversation_id: str) -> bool:
        """
        Delete a conversation entirely.
        
        Args:
            conversation_id: ID of the conversation to delete
            
        Returns:
            True if conversation was deleted, False if not found
        """
        if conversation_id in self.conversations:
            del self.conversations[conversation_id]
            return True
        return False
    
    def get_conversation_count(self) -> int:
        """
        Get the total number of active conversations.
        
        Returns:
            Number of conversations
        """
        return len(self.conversations)
    
    def list_conversations(self) -> List[str]:
        """
        List all conversation IDs.
        
        Returns:
            List of conversation IDs
        """
        return list(self.conversations.keys())
