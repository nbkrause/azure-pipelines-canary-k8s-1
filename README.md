# Canary deployments with Ambassador and Azure Pipelines

## Rationale

Azure pipelines have a deployment mechanism for doing _Canaries_. This mechanims can use
an existing [_service mesh_](https://smi-spec.io/) in your cluster but, if you are not using
Istio/Linkerd/etc., it does it with regular _Pods_: it creates a new `Deployment` with the same
_labels_ but with the `image` being tested. Your existing `Service` will send traffic to the
old pods as well as to the new pods (as they both match the Service `selector`), and this will
be done proportionally to the number of replicas of each `Deployment`.

The main problem with this solution is the granularity of the traffic split. A canary for 10%
traffic would require 9 pods in the old deployment and 1 with the new one, something that is
sometimes neither possible nor desirable.

Ambassador can split traffic by assigning different weight to `Mappings`, as described
[here](https://www.getambassador.io/reference/canary/). This provides much finer grain
control over the traffic without the need to change the number of pods.

## Proposed solution

Instead of using the Azure pipelines facilities for splitting traffic with
new Pods, we have created a new [`canarize.py`](deploy/canarize.py) script that,
given the manifests with your `Service`/`Deployment`, a new `-canary` version of
those will be created. In addition, it will also create a `Mapping` that will send
traffic to the canary with the given _weight_.

## References

- [Canary deployment strategy for Kubernetes deployments](https://github.com/MicrosoftDocs/vsts-docs/blob/fc69779032416f5fe783409d25d75be372732640/docs/pipelines/ecosystems/kubernetes/canary-demo.md)
- [Deployment strategies](https://github.com/microsoft/azure-pipelines-yaml/blob/master/design/deployment-strategies.md)
- [Canary releases with Ambassador](https://www.getambassador.io/reference/canary/)

## Overview of this repository

* `./app`:

  `app.py` - Simple Flask based web server instrumented using Prometheus instrumentation library for Python   applications. A custom counter is set up for the number of 'good' and 'bad' responses given out based on the value of `success_rate` variable.

  `Dockerfile` - Used for building the image with each change made to `app.py`. With each change made to
  `app.py`, build pipeline (CI) is triggered and the image gets built and pushed to the container registry.

* `./manifests`:

  `deployment.yml` - Contains specification of the `sampleapp` `Deployment` workload corresponding
  to the image published earlier. This manifest file is used not just for the stable version of
  `Deployment` object, but for deriving the `-canary` variant of the workloads as well.

  `service.yml` - Creates a `sampleapp` `Service` for routing requests to the pods spun up by the `Deployment`.

  `mapping.yml` - Ambassador `Mapping` for routing all the requests to `/` to the `sampleapp` `Service`.

* `./misc`:

  `service-monitor.yml` - Used for setup of a `ServiceMonitor` object to set up Prometheus metric scraping.

  `fortio-deploy.yml` - Used for setup of fortio deployment that is subsequently used as a
  load-testing tool to send a stream of requests to the sampleapp service deployed earlier.
  With sampleapp service's selector being applicable for all the three pods resulting from
  the Deployment objects that get created during the course of this how-to guide - sampleapp,
  sampleapp-baseline and sampleapp-canary, the stream of requests sent to sampleapp get
  routed to pods under all these three deployments.

* `./misc`:

  `canarize.py` - Script for generating a Canary for a `Service`/`Deployment`.

## Preparing your cluster

* Create a Kubernetes cluster in Azure by following the
  [official docs](https://docs.microsoft.com/en-us/azure/aks/kubernetes-walkthrough-portal).
  We will assume your have created it in a _Resource group_ called `Ambassador-Azure-Pipeline`,
  and the cluster name will be `Ambassador-Azure-Pipeline`.
* Get the credentials for your Kuberentes cluster (using the _resource group_ and the _cluster name_):
  ```shell script
  $ az aks get-credentials --resource-group Ambassador-Azure-Pipeline --name Ambassador-Azure-Pipeline
  ```
* Install Ambassador in this cluster by following [the instructions](https://www.getambassador.io/user-guide/install/). For example,
  ```shell script
  edgectl install
  ```
* Install the prometheus operator. You can do it with Helm 3, with:
  ```shell script
  helm repo add bitnami https://charts.bitnami.com/bitnami
  helm install prometheus bitnami/prometheus-operator
  ```
  (You can access it with `kubectl port-forward --namespace default svc/prometheus-prometheus-oper-prometheus 9090:9090`)

## Preparing the repo

### Azure DevOps project

* Navigate to "_All services_" > "_Azure DevOps_", or go to `https://dev.azure.com` directly. Register a new project.

### Connections

* In your Azure DevOps project, navigate to "_Project settings_" > "_Service connections_", or go to `https://dev.azure.com/<user>/<project>/_settings/adminservices` directly. Then:
  - Create a new _Docker Registry_ connection, select `Azure Container Registry` and select
    one of the existing registries. Assign a name like `azurepipelinescanaryk8s`
  - Add another _Kubernetes_ service connection for connecting to your existing
    kubernetes cluster. Name it `k8sEnvironment`.

### Customizing the pipeline

* Review the variables in the `azure-pipelines.yml`, specially the `containerRegistry` and `environment`.
  Their values should match the service connections created previously.
* In `manifests/deployment.yml`, replace the `image` with your container registry's URL.

### Creating the pipeline

* In your Azure DevOps project, navigate to "_Pipelines_" > "_New pipeline_".
* Connect & Select your code location. _Azure Repos Git_ is a great option if you do not wish to open your GitHub account. It will however require you to push your repo to a new location.
* Review & Run!
