import streamlit as st
import os
from typing import List
from src.testing.test_orchestrator import TestOrchestrator
from src.models.testing_models import TestType

class TestSessionView:
    """
    Renders the UI for a test generation session.
    """
    
    def __init__(self, orchestrator: TestOrchestrator):
        self.orchestrator = orchestrator

    def render(self):
        st.header("🧪 DevGuard: AI Test Lab")
        
        # Session State Management
        if 'test_session_files' not in st.session_state:
            st.session_state.test_session_files = []
            
        # 1. File Selection
        self._render_file_selection()
        
        # 2. Generation Controls
        if st.session_state.test_session_files:
            st.divider()
            self._render_generation_controls()
            
        # 3. Review Interface
        if self.orchestrator.current_session and self.orchestrator.current_session.generated_tests:
            st.divider()
            self._render_review_interface()
            
        # 4. Execution Interface
        if self.orchestrator.current_session and self.orchestrator.current_session.get_approved_count() > 0:
            st.divider()
            self._render_execution_interface()

    def _render_file_selection(self):
        st.subheader("1. Select Target Files")
        
        # Simple file selector - could be improved with tree view later
        # For now, list python files in project
        project_path = st.session_state.get('project_path')
        if not project_path:
             st.warning("Please set a project path first.")
             return

        all_files = []
        for root, _, files in os.walk(project_path):
            for file in files:
                if file.endswith('.py') and 'test' not in file:
                     all_files.append(os.path.join(root, file))
        
        # Filter for display
        rel_files = [os.path.relpath(f, project_path) for f in all_files]
        
        selected_rel = st.multiselect(
            "Choose files to generate tests for:",
            options=rel_files,
            default=st.session_state.test_session_files,
            key="test_file_selector"
        )
        
        # Update session state
        st.session_state.test_session_files = selected_rel
        
        if selected_rel:
            st.info(f"Selected {len(selected_rel)} files.")

    def _render_generation_controls(self):
        st.subheader("2. Generation Settings")
        
        col1, col2 = st.columns(2)
        with col1:
            test_type = st.selectbox(
                "Test Type",
                options=[t.value for t in TestType],
                index=0
            )
        
        with col2:
            st.write("") 
            st.write("")
            if st.button("🚀 Generate Tests", type="primary", use_container_width=True):
                self._run_generation(test_type)

    def _run_generation(self, test_type_str: str):
        selected_rel = st.session_state.test_session_files
        project_path = st.session_state.project_path
        abs_paths = [os.path.join(project_path, f) for f in selected_rel]
        
        # Start Session
        self.orchestrator.start_session(abs_paths)
        
        # Analysis
        with st.status("Analyzing files...", expanded=True) as status:
            self.orchestrator.analyze_selected_files()
            status.write("Analysis complete. Identifying testable elements...")
            
            elements = self.orchestrator.current_session.identified_elements
            st.write(f"Found {len(elements)} testable elements (functions/methods).")
            
            # Generation Loop
            progress_bar = st.progress(0)
            for i, (eid, element) in enumerate(elements.items()):
                status.write(f"Generating tests for `{element.name}`...")
                self.orchestrator.generate_tests_for_element(eid, TestType(test_type_str))
                progress_bar.progress((i + 1) / len(elements))
                
            status.update(label="Generation Complete!", state="complete", expanded=False)
            st.rerun()

    def _render_review_interface(self):
        session = self.orchestrator.current_session
        st.subheader(f"3. Review Generated Tests ({len(session.generated_tests)} generated)")
        
        # Metrics
        col1, col2, col3 = st.columns(3)
        col1.metric("Pending", session.get_pending_count())
        col2.metric("Approved", session.get_approved_count())
        col3.metric("Rejected", sum(1 for t in session.generated_tests.values() if t.status == "rejected"))

        # Bulk Actions
        b_col1, b_col2 = st.columns(2)
        if b_col1.button("✅ Approve All Pending"):
            for t in session.generated_tests.values():
                if t.status == "pending":
                    t.status = "approved"
            st.rerun()
            
        if b_col2.button("🚫 Reject All Pending"):
            for t in session.generated_tests.values():
                if t.status == "pending":
                    t.status = "rejected"
            st.rerun()

        st.divider()

        # Individual Review
        # Pagination or list all? List all for now, maybe in expanders
        
        pending_tests = [t for t in session.generated_tests.values() if t.status == "pending"]
        reviewed_tests = [t for t in session.generated_tests.values() if t.status != "pending"]
        
        if pending_tests:
            st.write("### Pending Review")
            for test in pending_tests:
                self._render_test_card(test)
        
        if reviewed_tests:
            with st.expander("View Reviewed Tests"):
                for test in reviewed_tests:
                    self._render_test_card(test)
                    
        # Save Button
        if session.get_approved_count() > 0:
            if st.button(f"💾 Save {session.get_approved_count()} Approved Tests to Disk", type="primary"):
                count = self.orchestrator.save_approved_tests()
                st.success(f"Saved {count} test files to `tests/` directory.")

    def _render_test_card(self, test):
        element = self.orchestrator.current_session.identified_elements[test.target_element_id]
        
        # Color code status
        status_color = "blue"
        if test.status == "approved": status_color = "green"
        if test.status == "rejected": status_color = "red"
        
        with st.container():
            st.markdown(f"#### `{element.name}` <span style='color:{status_color}'>[{test.status.upper()}]</span>", unsafe_allow_html=True)
            st.caption(f"Source: {os.path.basename(element.file_path)}")
            
            tab_code, tab_preview = st.tabs(["Generated Test", "Original Code"])
            
            with tab_code:
                new_code = st.text_area("Test Code", value=test.test_code, height=300, key=f"code_{test.test_id}")
                if new_code != test.test_code:
                    self.orchestrator.update_test_code(test.test_id, new_code)
                    
            with tab_preview:
                st.code(element.content, language="python")
                
            # Actions
            c1, c2, c3 = st.columns([1, 1, 4])
            if c1.button("Approve", key=f"app_{test.test_id}", type="primary" if test.status=="pending" else "secondary"):
                self.orchestrator.approve_test(test.test_id)
                st.rerun()
            if c2.button("Reject", key=f"rej_{test.test_id}"):
                self.orchestrator.reject_test(test.test_id)
                st.rerun()
                
            st.divider()

    def _render_execution_interface(self):
        st.subheader("4. Run Verification")
        
        if st.button("▶️ Run Approved Tests On-Device", type="primary"):
            with st.spinner("Running tests with pytest..."):
                results = self.orchestrator.run_verification()
            
            st.success("Test execution complete!")
            
            # Display Results
            passed = sum(1 for r in results.values() if r.passed)
            failed = len(results) - passed
            
            c1, c2 = st.columns(2)
            c1.metric("Tests Passed", passed)
            c2.metric("Tests Failed", failed)
            
            for path, res in results.items():
                icon = "✅" if res.passed else "❌"
                with st.expander(f"{icon} {os.path.basename(path)}"):
                    st.code(res.output)
