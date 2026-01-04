import os
import streamlit as st
from src.documentation.ui.file_selector import FileSelector
from src.structure_analyzer import StructureAnalyzer
from src.documentation.orchestrator import DocumentationOrchestrator
from src.documentation.analysis_agent import AnalysisAgent
from src.documentation.context_agent import ContextAgent
from src.documentation.documentation_agent import DocumentationAgent
from src.documentation.review_manager import ReviewManager

# Page configuration
st.set_page_config(
    page_title="CodeGuardian - Documentation Generator",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ CodeGuardian")
st.caption("Smart Code Documentation & Analysis Assistant")

# Initialize session state for workflow
if 'workflow_stage' not in st.session_state:
    st.session_state.workflow_stage = 'project_selection'

if 'selected_files' not in st.session_state:
    st.session_state.selected_files = None

if 'project_path' not in st.session_state:
    st.session_state.project_path = os.getcwd()

if 'analysis_done' not in st.session_state:
    st.session_state.analysis_done = False

# Stage 0: Project Selection & Analysis
if st.session_state.workflow_stage == 'project_selection':
    st.markdown("### Step 1: Project Setup")
    st.write("Please provide the path to your codebase directory.")
    
    # Path input
    col_input, col_btn = st.columns([3, 1])
    with col_input:
        path_input = st.text_input(
            "Codebase Directory Path", 
            value=st.session_state.project_path,
            help="Enter the absolute path to your project directory"
        )
    
    if st.button("Analyze Codebase", type="primary"):
        if os.path.isdir(path_input):
            st.session_state.project_path = path_input
            
            # Perform Analysis
            with st.spinner("Analyzing codebase structure..."):
                analyzer = StructureAnalyzer(path_input)
                analysis = analyzer.analyze_structure()
                st.session_state.structure_analysis = analysis
                st.session_state.analysis_done = True
        else:
            st.error(f"Directory not found: {path_input}")
            st.session_state.analysis_done = False

    # Display Analysis Results
    if st.session_state.get('analysis_done') and 'structure_analysis' in st.session_state:
        st.divider()
        st.subheader("📊 Structure Analysis")
        
        analysis = st.session_state.structure_analysis
        
        # Metrics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            score = analysis['score']
            delta_color = "normal"
            if score >= 8:
                delta_color = "normal" # Streamlit doesn't support success color in delta, but metric is fine
            elif score < 5:
                delta_color = "inverse"
            
            st.metric(
                "Structure Score", 
                f"{score}/10",
                help="Based on file organization and folder structure"
            )
            
        with col2:
            git_status = "Tracked" if analysis['has_git'] else "Not Tracked"
            st.metric("Git Status", git_status, delta="git" if analysis['has_git'] else None)
            
        with col3:
            st.metric("Total Files", analysis['total_files'])

        # Detailed feedback
        if score < 5:
            st.warning("⚠️ This codebase seems to be monolithic (files concentrated in one folder). Consider organizing into subdirectories for better structure.")
        elif score >= 8:
            st.success("✅ Excellent codebase organization!")
        else:
            st.info("ℹ️ Codebase structure is moderate.")

        # Continue Button
        st.divider()
        if st.button("Continue to File Selection →"):
            st.session_state.workflow_stage = 'file_selection'
            st.rerun()

# Stage 1: File Selection
elif st.session_state.workflow_stage == 'file_selection':
    st.markdown("### Step 2: Select Files")
    
    # Initialize and render file selector with the chosen path
    file_selector = FileSelector(root_path=st.session_state.project_path)
    
    # Show back button
    if st.button("← Back to Project Setup"):
        st.session_state.workflow_stage = 'project_selection'
        st.rerun()
        
    result = file_selector.render()
    
    # If files are confirmed, move to next stage
    if result:
        st.session_state.selected_files = result.selected_files
        st.session_state.files_by_language = result.files_by_language
        st.session_state.estimated_time = result.estimated_time_minutes
        st.session_state.workflow_stage = 'documentation_generation'
        st.rerun()

# Stage 2: Documentation Generation
elif st.session_state.workflow_stage == 'documentation_generation':
    st.markdown("### Step 3: Generate Documentation")
    
    # Display selection summary
    st.info(f"📁 Processing {len(st.session_state.selected_files)} files from `{st.session_state.project_path}`")
    
    col1, col2 = st.columns(2)
    with col1:
        st.write("**Files by Language:**")
        for lang, count in st.session_state.files_by_language.items():
            st.write(f"  • {lang}: {count}")
    
    with col2:
        st.write(f"**Estimated Time:** ~{st.session_state.estimated_time:.1f} min")
    
    st.divider()
    
    # Start generation button
    if st.button("🚀 Start Documentation Generation", type="primary"):
        st.info("🔄 This would start the documentation orchestrator...")
        st.write("Selected files:", st.session_state.selected_files)
        
        # In actual implementation, this would call:
        # orchestrator = DocumentationOrchestrator(...)
        # session = orchestrator.generate_documentation(
        #     file_paths=st.session_state.selected_files,
        #     progress_callback=progress_callback
        # )
    
    # Back button
    if st.button("← Back to File Selection"):
        st.session_state.workflow_stage = 'file_selection'
        st.rerun()

st.divider()
st.caption("CodeGuardian | Documentation Generator Integration")
