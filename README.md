# PyTorchJob Resource Viewer

A Streamlit-based web UI application for listing and monitoring PyTorchJob resources from OpenShift clusters. This application provides an intuitive interface to connect to OpenShift clusters and view distributed training jobs managed by the Kubeflow Training Operator.

## Features

- 🔗 **Flexible Authentication**: Connect using bearer tokens or kubeconfig files
- 📊 **Resource Overview**: View all PyTorchJob resources across namespaces
- 🔍 **Detailed Inspection**: Examine job specifications, status, and replica information
- 📈 **Status Monitoring**: Track job progress and replica status
- 🎛️ **Namespace Filtering**: Filter jobs by namespace or view all at once
- 📋 **Raw YAML View**: Inspect complete resource definitions
- 🎯 **Kueue Integration**: Display associated Workload resources and admission status
- ⏳ **Queue Monitoring**: Track job admission, resource allocation, and queue position

## Prerequisites

- Python 3.8 or higher
- Access to an OpenShift cluster with Kubeflow Training Operator installed
- Valid OpenShift credentials (bearer token)

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/opendatahub-io/distributed-workloads.git
   cd distributed-workloads/tests/kfto
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Starting the Application

Run the Streamlit application:

```bash
streamlit run test.py
```

The application will open in your default web browser at `http://localhost:8501`.

### Connecting to OpenShift

The application supports two authentication methods:

#### Method 1: Bearer Token Authentication

1. **Get your OpenShift credentials**:
   
   ```bash
   # Get your bearer token
   oc whoami --show-token
   
   # Get your cluster API URL
   oc cluster-info
   ```

2. **Fill in the connection form**:
   - **OpenShift API Server URL**: Example: `https://api.your-cluster.domain.com:6443`
   - **Bearer Token**: The token from `oc whoami --show-token`
   - **Verify SSL Certificate**: Uncheck if using self-signed certificates

3. **Click "Connect to Cluster"**

#### Method 2: Kubeconfig File Authentication

1. **Locate your kubeconfig file**:
   
   ```bash
   # Check if KUBECONFIG environment variable is set
   echo $KUBECONFIG
   
   # Or use the default location
   ls ~/.kube/config
   ```

2. **Use the kubeconfig in the application**:
   - **File Upload**: Click "Choose kubeconfig file" and select your kubeconfig file
   - **Manual Input**: Copy and paste the contents of your kubeconfig file
   - **Context**: Optionally specify a particular context (leave empty for default)

3. **Click "Connect to Cluster"**

### Viewing PyTorchJobs

Once connected, you can:

- **Browse all PyTorchJobs**: Select "All Namespaces" to see jobs across the entire cluster
- **Filter by namespace**: Choose a specific namespace from the dropdown
- **View job details**: Select any job for detailed information including:
  - Job metadata (name, namespace, creation time)
  - Replica configuration (Master, Worker replicas)
  - Current status and conditions
  - Resource requirements
  - Raw YAML definition

### Understanding the Interface

#### Summary Section
- Shows total number of PyTorchJobs
- Displays status distribution (Running, Succeeded, Failed, etc.)
- Shows Kueue admission status (Admitted, Pending, No Workload)

#### Jobs Table
- Lists all PyTorchJobs with key information
- Shows associated queue names and admission status
- Sortable and filterable
- Shows replica types and counts

#### Detailed View
- **Job Info Tab**: Basic metadata and configuration
- **Replica Details Tab**: Current state of job replicas
- **Conditions Tab**: Job lifecycle events and status changes
- **Kueue Workload Tab**: Associated Workload resource information
- **Raw Resources**: Complete YAML definitions for both PyTorchJob and Workload

## Resource Structure

### PyTorchJob Resources

PyTorchJobs are Kubernetes custom resources with the following key components:

#### Specification
- **pytorchReplicaSpecs**: Defines Master and Worker replicas
- **runPolicy**: Execution policies (cleanup, timeout, etc.)
- **nprocPerNode**: Number of processes per node

#### Status
- **conditions**: Current job state and transitions
- **replicaStatuses**: Status of individual replicas
- **startTime/completionTime**: Job timing information

### Kueue Workload Resources

When Kueue is installed, PyTorchJobs with queue labels automatically get associated Workload resources:

#### Specification
- **queueName**: Target LocalQueue for the job
- **podSets**: Resource requirements for different pod types
- **priorityClassName**: Job priority for scheduling

#### Status
- **admission**: Information about job admission to cluster queues
- **conditions**: Workload lifecycle events (Admitted, Pending, etc.)
- **queuedAt**: Timestamp when job was queued

#### Key Features
- **Resource Quotas**: Enforces cluster-wide resource limits
- **Fair Sharing**: Manages resource allocation between teams/users
- **Priority Scheduling**: Higher priority jobs can preempt lower priority ones
- **Gang Scheduling**: Ensures all job replicas are scheduled together

## Troubleshooting

### Connection Issues

**"Failed to connect to OpenShift cluster with token"**
- Verify your API server URL is correct
- Ensure your bearer token is valid and not expired
- Check if you have the necessary RBAC permissions
- Try disabling SSL verification for self-signed certificates

**"Failed to connect to OpenShift cluster with kubeconfig"**
- Verify your kubeconfig file is valid YAML
- Ensure the specified context exists in your kubeconfig
- Check if your kubeconfig contains expired certificates or tokens
- Verify cluster connectivity from your network location

**"PyTorchJob CRD not found"**
- Ensure Kubeflow Training Operator is installed in your cluster
- Verify you have permissions to access custom resources

**"No Kueue Workload associated with this PyTorchJob"**
- Check if Kueue is installed: `kubectl get crd workloads.kueue.x-k8s.io`
- Verify PyTorchJob has queue label: `kueue.x-k8s.io/queue-name`
- Ensure LocalQueue and ClusterQueue are properly configured
- Check if Workload was cleaned up after job completion

### Permission Issues

Your user account needs permissions to:
- List namespaces
- Get/List PyTorchJob custom resources
- Get/List Kueue Workload resources (if Kueue is installed)

Example RBAC configuration:
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: pytorchjob-workload-viewer
rules:
- apiGroups: ["kubeflow.org"]
  resources: ["pytorchjobs"]
  verbs: ["get", "list"]
- apiGroups: ["kueue.x-k8s.io"]
  resources: ["workloads", "localqueues", "clusterqueues"]
  verbs: ["get", "list"]
- apiGroups: [""]
  resources: ["namespaces"]
  verbs: ["get", "list"]
```

### Common Errors

1. **SSL Certificate errors**: Use `verify_ssl=False` option for self-signed certs (token auth)
2. **Token expiration**: Refresh your bearer token using `oc whoami --show-token`
3. **Network connectivity**: Ensure you can reach the OpenShift API server
4. **Invalid kubeconfig context**: List available contexts with `kubectl config get-contexts`
5. **Kubeconfig file format**: Ensure the file is valid YAML and follows kubeconfig format
6. **Context authentication**: Run `kubectl cluster-info` to verify your kubeconfig works

## Development

### Code Structure

- `OpenShiftConnector`: Handles cluster connection and API operations
- `create_connection_form()`: UI for cluster authentication
- `display_pytorchjobs()`: Main UI for resource listing and details
- `parse_pytorchjob()`: Transforms raw Kubernetes objects for display

### Dependencies

- **streamlit**: Web UI framework
- **kubernetes**: Official Kubernetes Python client
- **pandas**: Data manipulation and display
- **pyyaml**: YAML processing for resource display

## Example PyTorchJob

Here's an example of a PyTorchJob that would be displayed in the UI:

```yaml
apiVersion: kubeflow.org/v1
kind: PyTorchJob
metadata:
  name: pytorch-mnist
  namespace: default
spec:
  pytorchReplicaSpecs:
    Master:
      replicas: 1
      restartPolicy: OnFailure
      template:
        spec:
          containers:
          - name: pytorch
            image: kubeflow/pytorch-dist-mnist:latest
    Worker:
      replicas: 2
      restartPolicy: OnFailure
      template:
        spec:
          containers:
          - name: pytorch
            image: kubeflow/pytorch-dist-mnist:latest
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is part of the distributed-workloads repository and follows the same licensing terms. 