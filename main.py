import streamlit as st
import os
from typing import List, Optional
from dotenv import load_dotenv
import google.generativeai as genai
from src.structure_analyzer import StructureAnalyzer

# Load environment variables from .env file
load_dotenv()
from src.codebase_indexer import CodebaseIndexer, FileToIndex
from src.embedding_generator import EmbeddingGenerator
from src.vector_store import VectorStore
from src.query_engine import QueryEngine, Message
from src.answer_generator import AnswerGenerator
from src.conversation_manager import ConversationManager
from src.progress_tracker import ProgressTracker
from src.file_validator import FileValidator
from src.input_validator import InputValidator

# Documentation generator imports
from src.documentation.orchestrator import DocumentationOrchestrator
from src.documentation.analysis_agent import AnalysisAgent
from src.documentation.context_agent import ContextAgent
from src.documentation.documentation_agent import DocumentationAgent
from src.documentation.review_manager import ReviewManager
from src.documentation.error_handler import ErrorHandler
from src.documentation.gap_detector import GapDetector
from src.documentation.dependency_analyzer import DependencyAnalyzer
from src.documentation.template_engine import TemplateEngine
from src.documentation.export.export_module import ExportModule
from src.documentation.export.docstring_writer import DocstringWriter
from src.documentation.export.markdown_writer import MarkdownWriter
from src.documentation.export.html_writer import HTMLWriter
from src.documentation.ui.file_selector import FileSelector
from src.documentation.ui.progress_view import ProgressView
from src.documentation.ui.review_view import ReviewView
from src.documentation.ui.export_view import ExportView
from src.code_parser import CodeParser
from src.documentation.recursive_generator import RecursiveDocumentationGenerator
from src.testing.test_orchestrator import TestOrchestrator
from src.testing.ui.test_session_view import TestSessionView
from src.testing.test_validator import TestValidator
from src.testing.test_runner import TestRunner
from src.testing.test_generator import TestGenerator
from src.testing.test_analyzer import TestAnalyzer

# Page configuration
st.set_page_config(
    page_title="CodeGuardian AI",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for code snippet styling
st.markdown("""
<style>
    .code-badge {
        display: inline-block;
        background-color: #f0f2f6;
        border: 1px solid #d0d4db;
        border-radius: 4px;
        padding: 2px 8px;
        margin: 2px;
        font-size: 0.85em;
        font-family: monospace;
    }
    
    .file-reference {
        background-color: #e8f4f8;
        border-left: 3px solid #1f77b4;
        padding: 8px 12px;
        margin: 8px 0;
        border-radius: 4px;
    }
    
    .stChatMessage {
        padding: 1rem;
    }
    
    .upload-section {
        background-color: #f8f9fa;
        padding: 20px;
        border-radius: 8px;
        margin-bottom: 20px;
    }
    
    .stats-card {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 8px;
        border: 1px solid #e0e0e0;
        margin-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'messages' not in st.session_state:
    st.session_state.messages = []

if 'conversation_manager' not in st.session_state:
    st.session_state.conversation_manager = ConversationManager()
    st.session_state.conversation_id = st.session_state.conversation_manager.create_conversation()

if 'collection_name' not in st.session_state:
    st.session_state.collection_name = "default_collection"

if 'indexing_status' not in st.session_state:
    st.session_state.indexing_status = {
        'is_indexing': False,
        'progress': 0.0,
        'current_file': None,
        'files_processed': 0,
        'total_files': 0,
        'errors': []
    }

if 'collection_stats' not in st.session_state:
    st.session_state.collection_stats = {
        'files_indexed': 0,
        'chunks_stored': 0
    }

if 'vector_store' not in st.session_state:
    st.session_state.vector_store = VectorStore()

if 'embedding_generator' not in st.session_state:
    st.session_state.embedding_generator = EmbeddingGenerator()

# Documentation generator session state
if 'doc_workflow_stage' not in st.session_state:
    st.session_state.doc_workflow_stage = 'file_selection'  # file_selection, progress, review, export

if 'doc_session' not in st.session_state:
    st.session_state.doc_session = None

if 'doc_session_id' not in st.session_state:
    st.session_state.doc_session_id = None

if 'doc_orchestrator' not in st.session_state:
    # Initialize documentation orchestrator and components
    try:
        google_api_key = os.getenv("GOOGLE_API_KEY")
        if google_api_key:
            # Configure Gemini
            genai.configure(api_key=google_api_key)
            gemini_model = genai.GenerativeModel("gemini-3-flash-preview")
            
            # Initialize all components
            code_parser = CodeParser()
            gap_detector = GapDetector()
            dependency_analyzer = DependencyAnalyzer()
            template_engine = TemplateEngine()
            error_handler = ErrorHandler()
            review_manager = ReviewManager()
            
            # Initialize agents
            analysis_agent = AnalysisAgent(code_parser, gap_detector)
            context_agent = ContextAgent(
                dependency_analyzer,
                st.session_state.vector_store,
                st.session_state.embedding_generator,
                st.session_state.collection_name
            )
            documentation_agent = DocumentationAgent(
                gemini_model,
                template_engine
            )
            
            # Initialize export module
            docstring_writer = DocstringWriter()
            markdown_writer = MarkdownWriter()
            html_writer = HTMLWriter()
            export_module = ExportModule(docstring_writer, markdown_writer, html_writer)
            
            # Initialize orchestrator
            st.session_state.doc_orchestrator = DocumentationOrchestrator(
                analysis_agent,
                context_agent,
                documentation_agent,
                review_manager,
                error_handler
            )
            st.session_state.doc_review_manager = review_manager
            st.session_state.doc_export_module = export_module
        else:
            st.session_state.doc_orchestrator = None
            st.session_state.doc_review_manager = None
            st.session_state.doc_export_module = None
    except Exception as e:
        st.session_state.doc_orchestrator = None
        st.session_state.doc_review_manager = None
        st.session_state.doc_export_module = None
        st.error(f"Error initializing documentation orchestrator: {str(e)}")

# Initialize DevGuard Testing Orchestrator
if 'test_orchestrator' not in st.session_state:
    try:
        # Initialize test components
        q_engine = QueryEngine(
             embedding_generator=st.session_state.embedding_generator,
             vector_store=st.session_state.vector_store,
             collection_name=st.session_state.collection_name
        )
        
        google_api_key = os.getenv("GOOGLE_API_KEY")
        
        gen = TestGenerator(api_key=google_api_key, query_engine=q_engine)
        orch = TestOrchestrator(
            test_analyzer=TestAnalyzer(),
            test_generator=gen,
            test_validator=TestValidator(),
            test_runner=TestRunner()
        )
        st.session_state.test_orchestrator = orch
    except Exception as e:
        print(f"Failed to init test orchestrator: {e}")
        st.session_state.test_orchestrator = None

# Sidebar
with st.sidebar:
    st.header("⚙️ Settings")
    
    # Collection name input
    collection_name_input = st.text_input(
        "Collection Name",
        value=st.session_state.collection_name,
        help="Name for your codebase collection (alphanumeric, underscores, and hyphens only)",
        key="sidebar_collection_name"
    )
    
    # Validate and sanitize collection name
    if collection_name_input != st.session_state.collection_name:
        is_valid, error_msg = InputValidator.validate_collection_name(collection_name_input)
        if is_valid:
            st.session_state.collection_name = collection_name_input
        else:
            st.warning(f"⚠️ {error_msg}")
            # Auto-sanitize and suggest
            sanitized = InputValidator.sanitize_collection_name(collection_name_input)
            if sanitized != collection_name_input:
                st.info(f"💡 Suggested name: `{sanitized}`")
                if st.button("Use suggested name"):
                    st.session_state.collection_name = sanitized
                    st.rerun()
    
    st.divider()
    
    # Collection statistics
    st.subheader("📊 Statistics")
    
    # Display stats in cards
    st.markdown(
        f'<div class="stats-card">'
        f'<strong>Files Indexed:</strong> {st.session_state.collection_stats["files_indexed"]}'
        f'</div>',
        unsafe_allow_html=True
    )
    
    st.markdown(
        f'<div class="stats-card">'
        f'<strong>Code Chunks:</strong> {st.session_state.collection_stats["chunks_stored"]}'
        f'</div>',
        unsafe_allow_html=True
    )
    
    # Indexing status indicator
    if st.session_state.indexing_status['is_indexing']:
        st.markdown(
            '<div class="stats-card" style="background-color: #fff3cd; border-color: #ffc107;">'
            '<strong>Status:</strong> ⚡ Indexing...'
            '</div>',
            unsafe_allow_html=True
        )
    elif st.session_state.collection_stats['chunks_stored'] > 0:
        st.markdown(
            '<div class="stats-card" style="background-color: #d4edda; border-color: #28a745;">'
            '<strong>Status:</strong> ✅ Ready'
            '</div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            '<div class="stats-card" style="background-color: #f8d7da; border-color: #dc3545;">'
            '<strong>Status:</strong> ⚠️ No data indexed'
            '</div>',
            unsafe_allow_html=True
        )
    
    st.divider()
    
    # Controls
    st.subheader("🎛️ Controls")
    
    # New Conversation button
    if st.button("🔄 New Conversation", use_container_width=True, disabled=st.session_state.indexing_status['is_indexing']):
        # Clear messages
        st.session_state.messages = []
        
        # Create new conversation
        st.session_state.conversation_id = st.session_state.conversation_manager.create_conversation()
        
        st.success("Started new conversation!")
        st.rerun()
    
    # Clear Index button
    if st.button("🗑️ Clear Index", use_container_width=True, type="secondary", disabled=st.session_state.indexing_status['is_indexing']):
        if st.session_state.collection_stats['chunks_stored'] > 0:
            # Delete collection
            success = st.session_state.vector_store.delete_collection(st.session_state.collection_name)
            
            if success:
                # Reset stats
                st.session_state.collection_stats['files_indexed'] = 0
                st.session_state.collection_stats['chunks_stored'] = 0
                
                # Clear messages
                st.session_state.messages = []
                
                # Create new conversation
                st.session_state.conversation_id = st.session_state.conversation_manager.create_conversation()
                
                # Reset indexing status
                st.session_state.indexing_status['progress'] = 0.0
                st.session_state.indexing_status['errors'] = []
                
                st.success("Index cleared successfully!")
                st.rerun()
            else:
                st.error("Failed to clear index")
        else:
            st.warning("No index to clear")
    
    st.divider()
    
    # Help section
    with st.expander("ℹ️ Help"):
        st.markdown("""
        **How to use:**
        1. Upload your code files (.py, .js, .jsx, .ts, .tsx)
        2. Click "Start Indexing" to process files
        3. Ask questions about your codebase
        4. View source references for each answer
        
        **Tips:**
        - Use specific questions for better results
        - Ask follow-up questions for deeper understanding
        - Check source references to verify answers
        """)
    
    # API Key status
    st.divider()
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if google_api_key:
        st.success("✅ GOOGLE_API_KEY configured")
    else:
        st.error("❌ GOOGLE_API_KEY not found")


# Initialize project path in session state
if 'project_path' not in st.session_state:
    st.session_state.project_path = None

# Initialize path input in session state if not present
if 'path_input_value' not in st.session_state:
    st.session_state.path_input_value = ""

# Setup Screen if no project path
if not st.session_state.project_path:
    st.title("🚀 CodeGuardian Setup")
    st.markdown("Please select the codebase project directory to begin.")
    
    # Use columns for a better layout
    col1, col2 = st.columns([3, 1])
    with col1:
        path_input = st.text_input("Project Directory Path", placeholder="e.g., /path/to/your/project", key="path_input_value")
    
    with col2:
        # Add spacing to align button with text input
        st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
        
        def browse_callback():
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.wm_attributes('-topmost', 1)
                folder_path = filedialog.askdirectory(master=root)
                root.destroy()
                if folder_path:
                    st.session_state.path_input_value = folder_path
            except Exception as e:
                print(f"Error opening file picker: {e}")

        st.button("📂 Browse", help="Select a folder from your computer", use_container_width=True, on_click=browse_callback)
    
    if st.button("Set Project Path", type="primary"):
        # Get value from session state key
        current_input = st.session_state.path_input_value
        if current_input and os.path.isdir(current_input):
            st.session_state.project_path = os.path.abspath(current_input)
            st.success(f"Project path set to: {st.session_state.project_path}")
            st.rerun()
        else:
            st.error("Please enter a valid directory path.")
            
    st.info("👉 Enter the absolute path to your local project folder.")
    st.stop()

# Main title
st.title("🛡️ CodeGuardian AI")
st.markdown(f"**Current Project:** `{st.session_state.project_path}`")
if st.button("Change Project", type="secondary", key="change_project_btn"):
    st.session_state.project_path = None
    st.rerun()

# Analyze codebase structure
if 'structure_analysis' not in st.session_state or st.session_state.get('last_analyzed_path') != st.session_state.project_path:
    with st.spinner("Analyzing codebase structure..."):
        analyzer = StructureAnalyzer(st.session_state.project_path)
        st.session_state.structure_analysis = analyzer.analyze_structure()
        st.session_state.last_analyzed_path = st.session_state.project_path

analysis = st.session_state.structure_analysis

# Display analysis results
with st.expander("📊 Codebase Structure Analysis", expanded=True):
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            "Structure Score", 
            f"{analysis['score']}/10",
            help="Based on file organization and git tracking"
        )
    
    with col2:
        git_status = "Active" if analysis['has_git'] else "Not Detected"
        st.metric("Git Tracking", git_status)
        
    with col3:
        st.metric("Total Files", analysis['total_files'])
    
    if analysis['score'] < 5.0:
        st.warning("⚠️ This codebase appears to be monolithic. Consider organizing files into structured folders for better maintainability.")
    elif analysis['score'] >= 8.0:
        st.success("✅ Excellent codebase structure detected!")
    else:
        st.info("ℹ️ Good codebase structure.")

# Create tabs for different features
tab1, tab2, tab3 = st.tabs(["💬 Q&A Chat", "📝 Documentation Forge", "🧪 DevGuard Testing"])

# Tab 1: Q&A System
with tab1:
    st.markdown("Interact with your codebase using AI.")
    
    # File scanning section
    st.subheader("📂 Project Files")
    
    project_path = st.session_state.project_path
    file_validator = FileValidator()
    found_files = []
    total_size = 0
    
    exclude_dirs = {'.git', '__pycache__', 'node_modules', 'venv', '.venv', 'env', '.env', 'dist', 'build', '.idea', '.vscode', 'site-packages'}
    
    # Scan directory
    if project_path and os.path.exists(project_path):
        with st.spinner("Scanning project files..."):
            for root, dirs, files in os.walk(project_path):
                # Skip excluded directories
                dirs[:] = [d for d in dirs if d not in exclude_dirs]
                
                for file in files:
                    if file_validator.is_supported_type(file):
                        full_path = os.path.join(root, file)
                        try:
                            size = os.path.getsize(full_path)
                            found_files.append({
                                'path': full_path,
                                'rel_path': os.path.relpath(full_path, project_path),
                                'size': size
                            })
                            total_size += size
                        except Exception:
                            continue
    
    if found_files:
        st.info(f"Found {len(found_files)} supported files in `{project_path}` (Total size: {total_size / (1024 * 1024):.2f} MB)")
        
        with st.expander("View Found Files"):
            for f in found_files:
                st.text(f"📄 {f['rel_path']}")
        
        # Start indexing button
        if not st.session_state.indexing_status['is_indexing']:
            if st.button("🚀 Start Indexing", type="primary", use_container_width=True):
                try:
                    files_to_index = []
                    errors = []
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for i, f_info in enumerate(found_files):
                        try:
                            status_text.text(f"Reading: {f_info['rel_path']}")
                            progress_bar.progress((i + 1) / len(found_files))
                            
                            with open(f_info['path'], 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                            
                            files_to_index.append(FileToIndex(
                                file_path=f_info['rel_path'].replace('\\', '/'), # Normalize to forward slashes
                                content=content,
                                file_size=f_info['size']
                            ))
                        except Exception as e:
                            errors.append(f"Failed to read {f_info['rel_path']}: {str(e)}")
                    
                    status_text.empty()
                    progress_bar.empty()
                    
                    if not files_to_index:
                        st.error("No files could be read successfully.")
                    else:
                        if errors:
                            st.warning(f"Skipped {len(errors)} files due to read errors.")
                        
                        # Update indexing status
                        st.session_state.indexing_status['is_indexing'] = True
                        st.session_state.indexing_status['total_files'] = len(files_to_index)
                        st.session_state.indexing_status['files_processed'] = 0
                        st.session_state.indexing_status['errors'] = []
                    
                        # Store files for processing
                        st.session_state.files_to_index = files_to_index
                    
                        st.rerun()
                except Exception as e:
                    st.error(f"Failed to prepare files for indexing: {str(e)}")
    else:
        st.warning(f"No supported code files found in `{project_path}`.")

    # Indexing progress display
    if st.session_state.indexing_status['is_indexing']:
        st.divider()
        st.subheader("⚡ Indexing in Progress")
    
        # Progress bar
        progress_percentage = st.session_state.indexing_status['progress']
        st.progress(progress_percentage / 100.0)
    
        # Current file being processed
        if st.session_state.indexing_status['current_file']:
            st.info(f"📄 Processing: **{st.session_state.indexing_status['current_file']}**")
    
        # Files processed count
        files_processed = st.session_state.indexing_status['files_processed']
        total_files = st.session_state.indexing_status['total_files']
        st.write(f"**Progress:** {files_processed} / {total_files} files processed ({progress_percentage:.1f}%)")
    
        # Process files if we have them
        if 'files_to_index' in st.session_state and st.session_state.files_to_index:
            try:
                # Create progress callback
                def progress_callback(current_file, processed, total):
                    st.session_state.indexing_status['current_file'] = current_file
                    st.session_state.indexing_status['files_processed'] = processed
                    st.session_state.indexing_status['progress'] = (processed / total * 100) if total > 0 else 0
            
                # Run indexing
                indexer = CodebaseIndexer(
                    vector_store=st.session_state.vector_store,
                    embedding_generator=st.session_state.embedding_generator
                )
            
                with st.spinner("Indexing files..."):
                    result = indexer.index_files(
                        files=st.session_state.files_to_index,
                        collection_name=st.session_state.collection_name,
                        progress_callback=progress_callback
                    )
            
                # Update stats
                st.session_state.collection_stats['files_indexed'] = result.files_processed
                st.session_state.collection_stats['chunks_stored'] = result.chunks_created
            
                # Store errors
                st.session_state.indexing_status['errors'] = result.errors
            
                # Mark as complete
                st.session_state.indexing_status['is_indexing'] = False
                st.session_state.indexing_status['progress'] = 100.0
                st.session_state.indexing_status['current_file'] = None
            
                # Clear files
                del st.session_state.files_to_index
            
            except Exception as e:
                st.error(f"Critical error during indexing: {str(e)}")
                st.session_state.indexing_status['is_indexing'] = False
                st.session_state.indexing_status['errors'].append({
                    'file': 'system',
                    'error': str(e),
                    'stage': 'indexing_pipeline'
                })
                if 'files_to_index' in st.session_state:
                    del st.session_state.files_to_index
        
            st.rerun()

    # Show completion notification
    if (not st.session_state.indexing_status['is_indexing'] and 
        st.session_state.indexing_status['progress'] == 100.0 and
        st.session_state.collection_stats['files_indexed'] > 0):
    
        st.divider()
        st.success(f"✅ Indexing completed! {st.session_state.collection_stats['files_indexed']} files indexed, {st.session_state.collection_stats['chunks_stored']} chunks created.")
    
        # Show errors if any
        if st.session_state.indexing_status['errors']:
            with st.expander(f"⚠️ {len(st.session_state.indexing_status['errors'])} error(s) occurred"):
                for error in st.session_state.indexing_status['errors']:
                    st.error(f"**{error['file']}** ({error['stage']}): {error['error']}")
    
        # Reset progress for next indexing
        if st.button("Clear Status"):
            st.session_state.indexing_status['progress'] = 0.0
            st.session_state.indexing_status['errors'] = []
            st.rerun()

    # Chat interface
    st.divider()
    st.subheader("💬 AI Q&A Chat")

    # Only show chat if files are indexed
    if st.session_state.collection_stats['chunks_stored'] > 0:
        # Display conversation history
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"], unsafe_allow_html=True)
            
                # Display sources if available
                if "sources" in message and message["sources"]:
                    with st.expander("📎 Source References"):
                        for source in message["sources"]:
                            st.markdown(
                                f'<div class="file-reference">'
                                f'<strong>{source["file_path"]}</strong> '
                                f'<span class="code-badge">Lines {source["start_line"]}-{source["end_line"]}</span> '
                                f'<span class="code-badge">{source["chunk_type"]}</span>'
                                f'</div>',
                                unsafe_allow_html=True
                            )
    
        # Question input
        if question_input := st.chat_input("Ask about your code..."):
            # Validate question
            is_valid, error_msg = InputValidator.validate_question(question_input)
        
            if not is_valid:
                st.error(f"Invalid question: {error_msg}")
                st.stop()
        
            # Sanitize question
            question = InputValidator.sanitize_question(question_input)
        
            # Add user message to chat
            st.session_state.messages.append({"role": "user", "content": question})
        
            # Add to conversation manager
            st.session_state.conversation_id = st.session_state.conversation_manager.create_conversation() if 'conversation_id' not in st.session_state else st.session_state.conversation_id
            st.session_state.conversation_manager.add_message(
                st.session_state.conversation_id,
                "user",
                question
            )
        
            # Display user message
            with st.chat_message("user"):
                st.markdown(question)
        
            # Generate answer
            with st.chat_message("assistant"):
                message_placeholder = st.empty()
            
                try:
                    # Check if API key is set
                    google_api_key = os.getenv("GOOGLE_API_KEY")
                    if not google_api_key:
                        error_msg = "⚠️ **GOOGLE_API_KEY not found.** Please set your Gemini API key in the environment variables."
                        message_placeholder.error(error_msg)
                        st.session_state.messages.append({"role": "assistant", "content": error_msg})
                        st.stop()
                
                    # Initialize query engine and answer generator
                    query_engine = QueryEngine(
                        embedding_generator=st.session_state.embedding_generator,
                        vector_store=st.session_state.vector_store,
                        collection_name=st.session_state.collection_name
                    )
                
                    answer_generator = AnswerGenerator(api_key=google_api_key)
                
                    # Get conversation history
                    conversation_history = st.session_state.conversation_manager.get_messages(
                        st.session_state.conversation_id
                    )
                
                    # Retrieve relevant chunks
                    with st.spinner("Analyzing codebase..."):
                        retrieval_result = query_engine.query(
                            question=question,
                            conversation_context=conversation_history[:-1]  # Exclude current question
                        )
                
                    if not retrieval_result.chunks:
                        no_results_msg = """I couldn't find any relevant code for your question."""
                        message_placeholder.warning(no_results_msg)
                        st.session_state.messages.append({"role": "assistant", "content": no_results_msg})
                    else:
                        # Stream the answer
                        full_response = ""
                    
                        for chunk in answer_generator.generate_answer_stream(
                            question=question,
                            context_chunks=retrieval_result.chunks,
                            conversation_history=conversation_history[:-1]
                        ):
                            full_response += chunk
                            message_placeholder.markdown(full_response + "▌")
                    
                        message_placeholder.markdown(full_response)
                    
                        # Prepare sources for display
                        sources = [
                            {
                                "file_path": chunk.file_path,
                                "start_line": chunk.start_line,
                                "end_line": chunk.end_line,
                                "chunk_type": chunk.chunk_type
                            }
                            for chunk in retrieval_result.chunks
                        ]
                    
                        # Add to messages with sources
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": full_response,
                            "sources": sources
                        })
                    
                        # Add to conversation manager
                        st.session_state.conversation_manager.add_message(
                            st.session_state.conversation_id,
                            "assistant",
                            full_response
                        )
                    
                        # Display sources
                        with st.expander("📎 Source References"):
                            for source in sources:
                                st.markdown(
                                    f'<div class="file-reference">'
                                    f'<strong>{source["file_path"]}</strong> '
                                    f'<span class="code-badge">Lines {source["start_line"]}-{source["end_line"]}</span> '
                                    f'<span class="code-badge">{source["chunk_type"]}</span>'
                                    f'</div>',
                                    unsafe_allow_html=True
                                )
            
                except Exception as e:
                    error_msg = f"❌ **Error generating answer:** {str(e)}"
                    message_placeholder.error(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})

    else:
        st.info("👆 Upload and index some code files to get started.")

# Tab 2: Documentation Generator
with tab2:
    st.markdown("Automate codebase documentation with Gemini Forge.")
    
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
         st.error("❌ **GOOGLE_API_KEY not found.** Please set your Google API key in the .env file.")
    else:
        st.divider()
        
        # Input for directory path
        default_path = st.session_state.get('project_path', os.getcwd())
        target_dir = st.text_input("Target Directory", value=default_path, help="Absolute path to the directory to document", key="doc_target_dir")
        
        if st.button("🏗️ Forge Documentation", type="primary", use_container_width=True):
            if os.path.exists(target_dir) and os.path.isdir(target_dir):
                st.session_state.doc_workflow_stage = 'progress'
                st.session_state.target_dir = target_dir
                st.rerun()
            else:
                st.error("Invalid directory path.")

        # Documentation Workflow UI
        if 'doc_workflow_stage' in st.session_state:
            stage = st.session_state.doc_workflow_stage
            
            if stage == 'progress':
                st.subheader("⚡ Documentation Forging")
                
                progress_container = st.empty()
                status_container = st.empty()
                
                try:
                    # Recursive Generator
                    generator = RecursiveDocumentationGenerator(
                        api_key=google_api_key
                    )
                    
                    with st.spinner("Processing directory structure..."):
                        final_summary = generator.generate_docs_recursively(st.session_state.target_dir)
                    
                    st.success("Documentation forged successfully!")
                    st.markdown("### SUMMARY.md")
                    st.markdown(final_summary)
                    
                    if st.button("Reset Forge"):
                        st.session_state.doc_workflow_stage = 'file_selection'
                        st.rerun()
                        
                except Exception as e:
                    st.error(f"Forging failed: {str(e)}")
                    if st.button("Back"):
                        st.session_state.doc_workflow_stage = 'file_selection'
                        st.rerun()


# Tab 3: DevGuard Testing
with tab3:
    if st.session_state.test_orchestrator:
        view = TestSessionView(st.session_state.test_orchestrator)
        view.render()
    else:
        st.error("Test Orchestrator not initialized. Check logs.")
