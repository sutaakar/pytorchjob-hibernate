#!/usr/bin/env python3
"""
PyTorchJob Resource Viewer

A Streamlit-based UI application for listing and viewing PyTorchJob resources
from a connected OpenShift cluster. This application allows users to:
- Connect to OpenShift clusters using token authentication
- List all PyTorchJob resources across namespaces
- View detailed information about each PyTorchJob
- Monitor job status and replica information

Usage:
    streamlit run test.py

Requirements:
    pip install streamlit kubernetes pandas pyyaml
"""

import streamlit as st
import pandas as pd
import yaml
from datetime import datetime
from typing import Dict, List, Optional, Any

try:
    from kubernetes import client, config
    from kubernetes.client.rest import ApiException
except ImportError:
    st.error("Please install the kubernetes library: pip install kubernetes")
    st.stop()


class OpenShiftConnector:
    """Handles connection to OpenShift cluster and PyTorchJob operations."""
    
    def __init__(self):
        self.custom_api = None
        self.core_api = None
        self.connected = False
        self.cluster_info = {}

    def connect_with_token(self, api_server: str, token: str, verify_ssl: bool = True) -> bool:
        """
        Connect to OpenShift cluster using token authentication.
        
        Args:
            api_server: OpenShift API server URL
            token: Bearer token for authentication
            verify_ssl: Whether to verify SSL certificates
            
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            configuration = client.Configuration()
            configuration.host = api_server
            configuration.api_key = {"authorization": f"Bearer {token}"}
            configuration.verify_ssl = verify_ssl
            
            # Create API clients
            api_client = client.ApiClient(configuration)
            self.custom_api = client.CustomObjectsApi(api_client)
            self.core_api = client.CoreV1Api(api_client)
            
            # Test connection and get cluster info
            return self._test_connection_and_set_info(api_server)
            
        except Exception as e:
            st.error(f"Failed to connect to OpenShift cluster with token: {str(e)}")
            self.connected = False
            return False

    def connect_with_kubeconfig(self, kubeconfig_content: str, context: Optional[str] = None) -> bool:
        """
        Connect to OpenShift cluster using kubeconfig file.
        
        Args:
            kubeconfig_content: Content of the kubeconfig file
            context: Specific context to use (optional)
            
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            import tempfile
            import os
            
            # Create temporary file for kubeconfig
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                f.write(kubeconfig_content)
                kubeconfig_path = f.name
            
            try:
                # Load kubeconfig
                config.load_kube_config(config_file=kubeconfig_path, context=context)
                
                # Create API clients using the loaded config
                self.custom_api = client.CustomObjectsApi()
                self.core_api = client.CoreV1Api()
                
                # Get cluster info from kubeconfig
                try:
                    contexts, active_context = config.list_kube_config_contexts(config_file=kubeconfig_path)
                    if context and contexts:
                        for ctx in contexts:
                            if isinstance(ctx, dict) and ctx.get('name') == context:
                                active_context = ctx
                                break
                    
                    cluster_name = "unknown"
                    if isinstance(active_context, dict):
                        context_info = active_context.get('context', {})
                        if isinstance(context_info, dict):
                            cluster_name = context_info.get('cluster', 'unknown')
                    
                    server_url = "loaded from kubeconfig"
                except Exception:
                    cluster_name = "unknown"
                    server_url = "loaded from kubeconfig"
                
                # Test connection and get cluster info
                return self._test_connection_and_set_info(server_url, cluster_name)
                
            finally:
                # Clean up temporary file
                os.unlink(kubeconfig_path)
                
        except Exception as e:
            st.error(f"Failed to connect to OpenShift cluster with kubeconfig: {str(e)}")
            self.connected = False
            return False

    def _test_connection_and_set_info(self, server_url: str, cluster_name: str = "cluster") -> bool:
        """Test connection and set cluster info."""
        try:
            # Test connection by getting server version
            try:
                version_api = client.VersionApi()
                version_info = version_api.get_code()
                version_str = f"{getattr(version_info, 'major', 'unknown')}.{getattr(version_info, 'minor', 'unknown')}"
            except Exception:
                version_str = "unknown"
            
            self.cluster_info = {
                "server": server_url,
                "cluster": cluster_name,
                "version": version_str,
                "connected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self.connected = True
            return True
            
        except Exception as e:
            st.error(f"Failed to test cluster connection: {str(e)}")
            self.connected = False
            return False

    def get_namespaces(self) -> List[str]:
        """Get list of available namespaces."""
        if not self.connected or self.core_api is None:
            return []
        
        try:
            response = self.core_api.list_namespace()
            return [ns.metadata.name for ns in response.items]
        except ApiException as e:
            st.error(f"Error fetching namespaces: {e}")
            return []

    def get_pytorchjobs(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get PyTorchJob resources from the cluster.
        
        Args:
            namespace: Specific namespace to query, or None for all namespaces
            
        Returns:
            List of PyTorchJob resources as dictionaries
        """
        if not self.connected or self.custom_api is None:
            return []

        jobs = []
        try:
            if namespace:
                response = self.custom_api.list_namespaced_custom_object(
                    group="kubeflow.org",
                    version="v1",
                    namespace=namespace,
                    plural="pytorchjobs"
                )
                jobs.extend(response.get("items", []))
            else:
                response = self.custom_api.list_cluster_custom_object(
                    group="kubeflow.org",
                    version="v1", 
                    plural="pytorchjobs"
                )
                jobs.extend(response.get("items", []))
                
        except ApiException as e:
            if e.status == 404:
                st.warning("PyTorchJob CRD not found in cluster. Make sure Training Operator is installed.")
            else:
                st.error(f"Error fetching PyTorchJobs: {e}")
        except Exception as e:
            st.error(f"Unexpected error: {e}")
            
        return jobs

    def get_kueue_workloads(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get Kueue Workload resources from the cluster.
        
        Args:
            namespace: Specific namespace to query, or None for all namespaces
            
        Returns:
            List of Kueue Workload resources as dictionaries
        """
        if not self.connected or self.custom_api is None:
            return []

        workloads = []
        try:
            if namespace:
                response = self.custom_api.list_namespaced_custom_object(
                    group="kueue.x-k8s.io",
                    version="v1beta1",
                    namespace=namespace,
                    plural="workloads"
                )
                workloads.extend(response.get("items", []))
            else:
                response = self.custom_api.list_cluster_custom_object(
                    group="kueue.x-k8s.io",
                    version="v1beta1", 
                    plural="workloads"
                )
                workloads.extend(response.get("items", []))
                
        except ApiException as e:
            if e.status == 404:
                # Kueue might not be installed, which is okay
                pass
            else:
                st.warning(f"Error fetching Kueue Workloads: {e}")
        except Exception as e:
            st.warning(f"Unexpected error fetching Kueue Workloads: {e}")
            
        return workloads

    def find_workload_for_pytorchjob(self, pytorchjob: Dict[str, Any], workloads: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Find the Kueue Workload associated with a PyTorchJob.
        
        Args:
            pytorchjob: PyTorchJob resource
            workloads: List of Kueue Workload resources
            
        Returns:
            Associated Workload resource or None
        """
        job_metadata = pytorchjob.get("metadata", {})
        job_name = job_metadata.get("name", "")
        job_namespace = job_metadata.get("namespace", "")
        job_uid = job_metadata.get("uid", "")
        
        for workload in workloads:
            wl_metadata = workload.get("metadata", {})
            wl_namespace = wl_metadata.get("namespace", "")
            
            # Skip if not in the same namespace
            if job_namespace != wl_namespace:
                continue
            
            # Check owner references for direct association
            owner_refs = wl_metadata.get("ownerReferences", [])
            for owner_ref in owner_refs:
                if (owner_ref.get("kind") == "PyTorchJob" and 
                    owner_ref.get("name") == job_name and 
                    owner_ref.get("uid") == job_uid):
                    return workload
            
            # Fallback: check if workload name contains job name
            wl_name = wl_metadata.get("name", "")
            if job_name in wl_name:
                return workload
                
        return None

    def parse_pytorchjob(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Parse PyTorchJob resource into a readable format."""
        metadata = job.get("metadata", {})
        spec = job.get("spec", {})
        status = job.get("status", {})
        
        # Extract replica information
        replica_specs = spec.get("pytorchReplicaSpecs", {})
        replicas_info = {}
        for replica_type, replica_spec in replica_specs.items():
            replicas_info[replica_type] = {
                "replicas": replica_spec.get("replicas", 0),
                "restart_policy": replica_spec.get("restartPolicy", "N/A")
            }
        
        # Extract status information
        conditions = status.get("conditions", [])
        current_condition = conditions[-1] if conditions else {}
        job_status = current_condition.get("type", "Unknown")
        
        replica_statuses = status.get("replicaStatuses", {})
        
        # Check for Kueue queue label
        labels = metadata.get("labels", {})
        queue_name = labels.get("kueue.x-k8s.io/queue-name", "N/A")
        
        return {
            "name": metadata.get("name", "N/A"),
            "namespace": metadata.get("namespace", "N/A"),
            "created": metadata.get("creationTimestamp", "N/A"),
            "status": job_status,
            "replicas": replicas_info,
            "replica_statuses": replica_statuses,
            "run_policy": spec.get("runPolicy", {}),
            "nproc_per_node": spec.get("nprocPerNode", "auto"),
            "conditions": conditions,
            "queue_name": queue_name,
            "raw": job
        }

    def update_workload_active_status(self, workload_name: str, namespace: str, active: bool) -> bool:
        """
        Update the active status of a Kueue Workload.
        
        Args:
            workload_name: Name of the Kueue Workload
            namespace: Namespace of the Workload
            active: True to resume, False to hibernate
            
        Returns:
            bool: True if update successful, False otherwise
        """
        if not self.connected or self.custom_api is None:
            return False
        
        try:
            # Patch the workload with the new active status
            patch_body = {
                "spec": {
                    "active": active
                }
            }
            
            self.custom_api.patch_namespaced_custom_object(
                group="kueue.x-k8s.io",
                version="v1beta1",
                namespace=namespace,
                plural="workloads",
                name=workload_name,
                body=patch_body
            )
            
            action = "resumed" if active else "hibernated"
            st.success(f"✅ Workload '{workload_name}' has been {action}")
            return True
            
        except ApiException as e:
            st.error(f"Failed to update workload: {e}")
            return False
        except Exception as e:
            st.error(f"Unexpected error updating workload: {e}")
            return False

    def parse_kueue_workload(self, workload: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Kueue Workload resource into a readable format."""
        metadata = workload.get("metadata", {})
        spec = workload.get("spec", {})
        status = workload.get("status", {})
        
        # Extract active status
        active_status = spec.get("active", True)  # Default to True if not specified
        
        # Extract admission status
        conditions = status.get("conditions", [])
        admitted_condition = None
        for condition in conditions:
            if condition.get("type") == "Admitted":
                admitted_condition = condition
                break
        
        admission_status = "Unknown"
        admission_message = "N/A"
        if admitted_condition:
            if admitted_condition.get("status") == "True":
                admission_status = "Admitted"
            elif admitted_condition.get("status") == "False":
                admission_status = "Pending"
            admission_message = admitted_condition.get("message", "N/A")
        
        # Extract queue information
        queue_name = spec.get("queueName", "N/A")
        priority_class = spec.get("priorityClassName", "N/A")
        
        # Extract resource requirements
        pod_sets = spec.get("podSets", [])
        total_resources = {"cpu": 0, "memory": "0", "gpu": 0}
        
        for pod_set in pod_sets:
            count = pod_set.get("count", 0)
            template = pod_set.get("template", {})
            containers = template.get("spec", {}).get("containers", [])
            
            for container in containers:
                resources = container.get("resources", {})
                requests = resources.get("requests", {})
                
                if "cpu" in requests:
                    try:
                        cpu_val = requests["cpu"]
                        if isinstance(cpu_val, str):
                            if cpu_val.endswith("m"):
                                cpu_val = float(cpu_val[:-1]) / 1000
                            else:
                                cpu_val = float(cpu_val)
                        total_resources["cpu"] += cpu_val * count
                    except (ValueError, TypeError):
                        pass
                
                if "memory" in requests:
                    total_resources["memory"] = requests["memory"]
                
                if "nvidia.com/gpu" in requests:
                    try:
                        gpu_val = int(requests["nvidia.com/gpu"])
                        total_resources["gpu"] += gpu_val * count
                    except (ValueError, TypeError):
                        pass
        
        # Extract assignment information
        admission = status.get("admission", {})
        cluster_queue = admission.get("clusterQueue", "N/A")
        pod_set_assignments = admission.get("podSetAssignments", [])
        
        return {
            "name": metadata.get("name", "N/A"),
            "namespace": metadata.get("namespace", "N/A"),
            "created": metadata.get("creationTimestamp", "N/A"),
            "active_status": active_status,
            "admission_status": admission_status,
            "admission_message": admission_message,
            "queue_name": queue_name,
            "cluster_queue": cluster_queue,
            "priority_class": priority_class,
            "total_resources": total_resources,
            "pod_set_assignments": pod_set_assignments,
            "conditions": conditions,
            "raw": workload
        }


def create_connection_form() -> Optional[OpenShiftConnector]:
    """Create the connection form and handle cluster connection."""
    st.header("🔗 OpenShift Cluster Connection")
    
    connector = OpenShiftConnector()
    
    # Authentication method selection
    auth_method = st.radio(
        "Authentication Method",
        ["Bearer Token", "Kubeconfig File"],
        help="Choose how to authenticate with your OpenShift cluster"
    )
    
    if auth_method == "Bearer Token":
        with st.form("token_connection_form"):
            st.subheader("Token Authentication")
            
            api_server = st.text_input(
                "OpenShift API Server URL",
                placeholder="https://api.your-cluster.domain.com:6443",
                help="The URL of your OpenShift cluster API server"
            )
            
            token = st.text_input(
                "Bearer Token",
                type="password",
                placeholder="sha256~your-token-here",
                help="Get this from: oc whoami --show-token"
            )
            
            verify_ssl = st.checkbox(
                "Verify SSL Certificate",
                value=True,
                help="Uncheck if using self-signed certificates"
            )
            
            connect_button = st.form_submit_button("Connect to Cluster")
            
            if connect_button:
                if not api_server or not token:
                    st.error("Please provide both API server URL and token")
                    return None
                    
                with st.spinner("Connecting to cluster..."):
                    if connector.connect_with_token(api_server, token, verify_ssl):
                        st.success("✅ Successfully connected to OpenShift cluster!")
                        st.session_state['connector'] = connector
                        return connector
                    else:
                        return None
    
    else:  # Kubeconfig File
        with st.form("kubeconfig_connection_form"):
            st.subheader("Kubeconfig Authentication")
            
            st.markdown("**Upload your kubeconfig file or paste its content:**")
            
            # File uploader
            uploaded_file = st.file_uploader(
                "Choose kubeconfig file",
                type=['yaml', 'yml', 'config'],
                help="Upload your kubeconfig file (usually located at ~/.kube/config)"
            )
            
            # Text area for manual input
            kubeconfig_text = st.text_area(
                "Or paste kubeconfig content",
                placeholder="apiVersion: v1\nkind: Config\nclusters:\n...",
                height=150,
                help="Paste the contents of your kubeconfig file here"
            )
            
            # Context selection (will be populated after loading kubeconfig)
            context = st.text_input(
                "Context (optional)",
                placeholder="Leave empty to use default context",
                help="Specify a particular context from your kubeconfig"
            )
            
            connect_button = st.form_submit_button("Connect to Cluster")
            
            if connect_button:
                kubeconfig_content = ""
                
                # Get kubeconfig content from file or text area
                if uploaded_file is not None:
                    kubeconfig_content = uploaded_file.read().decode('utf-8')
                elif kubeconfig_text.strip():
                    kubeconfig_content = kubeconfig_text.strip()
                else:
                    st.error("Please provide kubeconfig either by uploading a file or pasting the content")
                    return None
                
                if kubeconfig_content:
                    with st.spinner("Connecting to cluster..."):
                        context_param = context.strip() if context.strip() else None
                        if connector.connect_with_kubeconfig(kubeconfig_content, context_param):
                            st.success("✅ Successfully connected to OpenShift cluster!")
                            st.session_state['connector'] = connector
                            return connector
                        else:
                            return None
    
    return None


def display_cluster_info(connector: OpenShiftConnector):
    """Display cluster connection information."""
    if connector.connected:
        st.success("🟢 Connected to OpenShift Cluster")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Server", connector.cluster_info.get("server", "N/A"))
        with col2:
            st.metric("Cluster", connector.cluster_info.get("cluster", "N/A"))
        with col3:
            st.metric("Version", connector.cluster_info.get("version", "N/A"))
        with col4:
            st.metric("Connected At", connector.cluster_info.get("connected_at", "N/A"))


def display_pytorchjobs(connector: OpenShiftConnector):
    """Display PyTorchJob resources in a table format."""
    st.header("🚀 PyTorchJob Resources")
    
    # Namespace selection
    namespaces = connector.get_namespaces()
    
    col1, col2 = st.columns([2, 1])
    with col1:
        selected_namespace = st.selectbox(
            "Select Namespace",
            options=["All Namespaces"] + namespaces,
            help="Choose a specific namespace or view all PyTorchJobs"
        )
    
    with col2:
        refresh_button = st.button("🔄 Refresh", help="Refresh PyTorchJob list")
    
    # Get PyTorchJobs and Kueue Workloads
    namespace = None if selected_namespace == "All Namespaces" else selected_namespace
    jobs = connector.get_pytorchjobs(namespace)
    workloads = connector.get_kueue_workloads(namespace)
    
    if not jobs:
        st.info("No PyTorchJob resources found in the selected namespace(s).")
        return
    
    # Parse jobs and workloads for display
    parsed_jobs = [connector.parse_pytorchjob(job) for job in jobs]
    parsed_workloads = [connector.parse_kueue_workload(wl) for wl in workloads]
    
    # Associate workloads with jobs
    jobs_with_workloads = []
    for job in jobs:
        parsed_job = connector.parse_pytorchjob(job)
        associated_workload = connector.find_workload_for_pytorchjob(job, workloads)
        parsed_workload = connector.parse_kueue_workload(associated_workload) if associated_workload else None
        jobs_with_workloads.append((parsed_job, parsed_workload))
    
    # Create summary table with Kueue info
    st.subheader(f"📊 Summary ({len(parsed_jobs)} jobs)")
    
    # Status distribution
    status_counts = {}
    admission_counts = {"Admitted": 0, "Pending": 0, "No Workload": 0}
    active_counts = {"Active": 0, "Hibernated": 0, "No Workload": 0}
    
    for job, workload in jobs_with_workloads:
        status = job["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
        
        if workload:
            admission_status = workload["admission_status"]
            if admission_status in admission_counts:
                admission_counts[admission_status] += 1
            else:
                admission_counts["Pending"] += 1
            
            # Count active status
            if workload["active_status"]:
                active_counts["Active"] += 1
            else:
                active_counts["Hibernated"] += 1
        else:
            admission_counts["No Workload"] += 1
            active_counts["No Workload"] += 1
    
    # Display job status
    st.write("**PyTorchJob Status:**")
    status_cols = st.columns(len(status_counts))
    for i, (status, count) in enumerate(status_counts.items()):
        with status_cols[i]:
            st.metric(status, count)
    
    # Display Kueue admission status if workloads exist
    if workloads:
        st.write("**Kueue Admission Status:**")
        admission_cols = st.columns(len(admission_counts))
        for i, (status, count) in enumerate(admission_counts.items()):
            with admission_cols[i]:
                # Use different colors for different statuses
                if status == "Admitted":
                    st.metric(f"✅ {status}", count)
                elif status == "Pending":
                    st.metric(f"⏳ {status}", count)
                else:
                    st.metric(f"➖ {status}", count)
        
        st.write("**Workload Active Status:**")
        active_cols = st.columns(len(active_counts))
        for i, (status, count) in enumerate(active_counts.items()):
            with active_cols[i]:
                # Use different colors for different statuses
                if status == "Active":
                    st.metric(f"🟢 {status}", count)
                elif status == "Hibernated":
                    st.metric(f"🟡 {status}", count)
                else:
                    st.metric(f"➖ {status}", count)
    
    # Detailed table with actions
    st.subheader("📋 PyTorchJob Details")
    
    # Create a custom table with action buttons
    for i, (job, workload) in enumerate(jobs_with_workloads):
        # Calculate total replicas
        total_replicas = sum(replica["replicas"] for replica in job["replicas"].values())
        replica_types = ", ".join(job["replicas"].keys())
        
        # Get Kueue information
        queue_name = job.get("queue_name", "N/A")
        admission_status = workload["admission_status"] if workload else "No Workload"
        active_status = "N/A"
        if workload:
            active_status = "🟢 Active" if workload["active_status"] else "🟡 Hibernated"
        
        # Create expandable row for each job
        with st.expander(
            f"**{job['name']}** ({job['namespace']}) - {job['status']} | {active_status}",
            expanded=False
        ):
            # Job details in columns
            info_col1, info_col2, info_col3, action_col = st.columns([2, 2, 2, 1.5])
            
            with info_col1:
                st.write(f"**Queue:** {queue_name}")
                st.write(f"**Admission:** {admission_status}")
                st.write(f"**Active:** {active_status}")
            
            with info_col2:
                st.write(f"**Replica Types:** {replica_types}")
                st.write(f"**Total Replicas:** {total_replicas}")
                st.write(f"**Nproc Per Node:** {job['nproc_per_node']}")
            
            with info_col3:
                st.write(f"**Status:** {job['status']}")
                st.write(f"**Created:** {job['created'][:19] if job['created'] != 'N/A' else 'N/A'}")
            
            with action_col:
                st.write("**Actions:**")
                
                if workload:
                    current_active = workload["active_status"]
                    workload_name = workload["name"]
                    workload_namespace = workload["namespace"]
                    
                    # Hibernate button
                    if current_active:
                        if st.button(
                            "🛑 Hibernate",
                            key=f"hibernate_{i}",
                            help=f"Pause workload for {job['name']}",
                            type="secondary"
                        ):
                            if connector.update_workload_active_status(workload_name, workload_namespace, False):
                                st.rerun()
                    else:
                        st.button(
                            "🛑 Hibernate",
                            key=f"hibernate_disabled_{i}",
                            help="Workload is already hibernated",
                            disabled=True
                        )
                    
                    # Resume button
                    if not current_active:
                        if st.button(
                            "▶️ Resume",
                            key=f"resume_{i}",
                            help=f"Resume workload for {job['name']}",
                            type="primary"
                        ):
                            if connector.update_workload_active_status(workload_name, workload_namespace, True):
                                st.rerun()
                    else:
                        st.button(
                            "▶️ Resume",
                            key=f"resume_disabled_{i}",
                            help="Workload is already active",
                            disabled=True
                        )
                else:
                    st.info("No Kueue Workload")
                    st.write("*Actions not available*")
    
    # Detailed view
    st.subheader("🔍 Detailed View")
    
    if jobs_with_workloads:
        job_names = [job["name"] for job, _ in jobs_with_workloads]
        selected_job_name = st.selectbox(
            "Select a PyTorchJob for detailed view",
            options=job_names
        )
        
        selected_job, selected_workload = next(
            (job, workload) for job, workload in jobs_with_workloads 
            if job["name"] == selected_job_name
        )
        
        # Create tabs for different sections
        tab1, tab2, tab3, tab4 = st.tabs(["📝 Job Info", "🔧 Replica Details", "📋 Conditions", "🎛️ Kueue Workload"])
        
        with tab1:
            # Display basic job information
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("PyTorchJob Information")
                st.write(f"**Name:** {selected_job['name']}")
                st.write(f"**Namespace:** {selected_job['namespace']}")
                st.write(f"**Status:** {selected_job['status']}")
                st.write(f"**Created:** {selected_job['created']}")
                st.write(f"**Nproc Per Node:** {selected_job['nproc_per_node']}")
                st.write(f"**Queue:** {selected_job.get('queue_name', 'N/A')}")
                
            with col2:
                st.subheader("🔧 Replica Configuration")
                for replica_type, replica_info in selected_job["replicas"].items():
                    st.write(f"**{replica_type}:**")
                    st.write(f"  - Replicas: {replica_info['replicas']}")
                    st.write(f"  - Restart Policy: {replica_info['restart_policy']}")
        
        with tab2:
            # Replica Status
            if selected_job["replica_statuses"]:
                st.subheader("📊 Current Replica Status")
                status_data = []
                for replica_type, status_info in selected_job["replica_statuses"].items():
                    status_data.append({
                        "Replica Type": replica_type,
                        "Active": status_info.get("active", 0),
                        "Failed": status_info.get("failed", 0),
                        "Succeeded": status_info.get("succeeded", 0)
                    })
                
                if status_data:
                    status_df = pd.DataFrame(status_data)
                    st.dataframe(status_df, use_container_width=True)
            else:
                st.info("No replica status information available.")
        
        with tab3:
            # PyTorchJob Conditions
            if selected_job["conditions"]:
                st.subheader("📋 PyTorchJob Conditions")
                for i, condition in enumerate(selected_job["conditions"]):
                    with st.expander(f"{condition.get('type', 'Unknown')} - {condition.get('status', 'Unknown')}"):
                        st.write(f"**Type:** {condition.get('type', 'Unknown')}")
                        st.write(f"**Status:** {condition.get('status', 'Unknown')}")
                        if condition.get("reason"):
                            st.write(f"**Reason:** {condition['reason']}")
                        if condition.get("message"):
                            st.write(f"**Message:** {condition['message']}")
                        if condition.get("lastTransitionTime"):
                            st.write(f"**Last Transition:** {condition['lastTransitionTime']}")
            else:
                st.info("No conditions available for this PyTorchJob.")
        
        with tab4:
            # Kueue Workload Information
            if selected_workload:
                st.subheader("🎛️ Kueue Workload Information")
                
                st.info("💡 **Tip:** Use the Hibernate/Resume buttons in the PyTorchJob Details section above for direct workload control.")
                
                # Basic workload info
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write("**Basic Information:**")
                    st.write(f"**Name:** {selected_workload['name']}")
                    st.write(f"**Namespace:** {selected_workload['namespace']}")
                    st.write(f"**Created:** {selected_workload['created']}")
                    st.write(f"**Queue:** {selected_workload['queue_name']}")
                    st.write(f"**Cluster Queue:** {selected_workload['cluster_queue']}")
                    
                    # Active Status display only
                    st.write("**Active Status:**")
                    is_active = selected_workload['active_status']
                    if is_active:
                        st.success("🟢 Active (Running)")
                    else:
                        st.warning("🟡 Hibernated (Paused)")
                    
                with col2:
                    st.write("**Admission Status:**")
                    if selected_workload['admission_status'] == "Admitted":
                        st.success(f"✅ {selected_workload['admission_status']}")
                    elif selected_workload['admission_status'] == "Pending":
                        st.warning(f"⏳ {selected_workload['admission_status']}")
                    else:
                        st.info(f"❓ {selected_workload['admission_status']}")
                    
                    if selected_workload['admission_message'] != "N/A":
                        st.write(f"**Message:** {selected_workload['admission_message']}")
                    
                    if selected_workload['priority_class'] != "N/A":
                        st.write(f"**Priority Class:** {selected_workload['priority_class']}")
                
                # Resource requirements
                st.subheader("💾 Resource Requirements")
                resources = selected_workload['total_resources']
                
                resource_col1, resource_col2, resource_col3 = st.columns(3)
                with resource_col1:
                    st.metric("CPU", f"{resources['cpu']:.2f}")
                with resource_col2:
                    st.metric("Memory", resources['memory'])
                with resource_col3:
                    st.metric("GPU", resources['gpu'])
                
                # Pod set assignments (if admitted)
                if selected_workload['pod_set_assignments']:
                    st.subheader("📦 Pod Set Assignments")
                    for i, assignment in enumerate(selected_workload['pod_set_assignments']):
                        with st.expander(f"Pod Set {i+1}"):
                            st.json(assignment)
                
                # Workload conditions
                if selected_workload['conditions']:
                    st.subheader("📋 Workload Conditions")
                    for condition in selected_workload['conditions']:
                        with st.expander(f"{condition.get('type', 'Unknown')} - {condition.get('status', 'Unknown')}"):
                            st.write(f"**Type:** {condition.get('type', 'Unknown')}")
                            st.write(f"**Status:** {condition.get('status', 'Unknown')}")
                            if condition.get("reason"):
                                st.write(f"**Reason:** {condition['reason']}")
                            if condition.get("message"):
                                st.write(f"**Message:** {condition['message']}")
                            if condition.get("lastTransitionTime"):
                                st.write(f"**Last Transition:** {condition['lastTransitionTime']}")
            else:
                st.info("No Kueue Workload associated with this PyTorchJob.")
                st.markdown("""
                **Possible reasons:**
                - Kueue is not installed in the cluster
                - PyTorchJob was not submitted with a queue label
                - Workload was cleaned up after job completion
                """)
        
        # Raw YAML in expandable sections
        st.subheader("📄 Raw Resources")
        col1, col2 = st.columns(2)
        
        with col1:
            with st.expander("🔧 PyTorchJob YAML"):
                st.code(yaml.dump(selected_job["raw"], default_flow_style=False), language="yaml")
        
        with col2:
            if selected_workload:
                with st.expander("🎛️ Kueue Workload YAML"):
                    st.code(yaml.dump(selected_workload["raw"], default_flow_style=False), language="yaml")
            else:
                st.info("No Workload YAML available")


def main():
    """Main application function."""
    st.set_page_config(
        page_title="PyTorchJob Viewer",
        page_icon="🚀",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("🚀 PyTorchJob Resource Viewer")
    st.markdown("Monitor and manage PyTorchJob resources in your OpenShift cluster")
    
    # Sidebar with connection info
    with st.sidebar:
        st.header("ℹ️ About")
        st.markdown("""
        This application allows you to:
        - Connect to OpenShift clusters
        - List PyTorchJob resources
        - View detailed job information
        - Monitor job status and replicas
        - Display associated Kueue Workloads
        - Track job admission and queue status
        - **Hibernate/Resume workloads** to manage resource usage
        """)
        
        st.header("🔧 Instructions")
        st.markdown("""
        **Token Authentication:**
        1. Get your OpenShift token:
           ```bash
           oc whoami --show-token
           ```
        2. Get your cluster API URL:
           ```bash
           oc cluster-info
           ```
        3. Enter credentials and connect
        
        **Kubeconfig Authentication:**
        1. Locate your kubeconfig file:
           ```bash
           echo $KUBECONFIG
           # or typically: ~/.kube/config
           ```
        2. Upload the file or copy its content
        3. Optionally specify a context
        4. Connect to cluster
        """)
        
        # Connection status in sidebar
        if 'connector' in st.session_state:
            connector = st.session_state['connector']
            if connector.connected:
                st.success("🟢 Connected")
                st.write(f"Server: {connector.cluster_info.get('server', 'N/A')}")
                if st.button("Disconnect"):
                    del st.session_state['connector']
                    st.rerun()
    
    # Main content
    if 'connector' not in st.session_state:
        connector = create_connection_form()
        if connector:
            st.rerun()
    else:
        connector = st.session_state['connector']
        display_cluster_info(connector)
        st.divider()
        display_pytorchjobs(connector)


if __name__ == "__main__":
    main()
