# An Envoy ExternalProcessor SDK in python

## Overview
Forked from [wrossmorrow/envoy-extproc-sdk](https://github.com/wrossmorrow/envoy-extproc-sdk)

[`envoy`](https://www.envoyproxy.io/), one of the most powerful and widely used reverse proxies, is able to query an [ExternalProcessor](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/ext_proc_filter) gRPC service in it's filter chain. This functionality opens the door to quickly and robustly implemently customized functions at the edge, instead of in targeted services. [Bond](www.bond.tech), for example, is using this functionality to implement authentication, API call logging, and write-request idempotency. While powerful, implementing these services still requires dealing with complicated `envoy` specs, managing information sharing across request phases, and an understanding of gRPC, none of which are exactly straightforward. 

**The purpose of this SDK is to make development of ExternalProcessors easy**. This SDK _certainly_ won't supply the most _performant_ edge functions. With the `docker compose` setup here we see an overhead of about 20ms/req with 6 processors in the filter chain, or maybe about 4-5ms/req per filter. Without a doubt, much better performance will come from eschewing the ease-of-use functionality here, packing processor functions together in one filter, implementing your filter in a compiled language, or even more likely _not using an ExternalProcessor at all_ but instead using a [WASM plugin](https://www.envoyproxy.io/docs/envoy/latest/api-v3/extensions/wasm/v3/wasm.proto) or registered [custom filter binary](https://github.com/envoyproxy/envoy-filter-example). Optimal performance isn't our goal; usability, maintainability, and low time-to-functionality is, and those aspects can often be more important than minimal latency. 

### Usage

Specifically we supply a `BaseExtProcService` that provides much of the boilerplate required to make this type of service. Here is a brief, untyped example of how to build one (based on `examples/decorated.py`):
```py
import logging
from envoy_extproc_sdk import BaseExtProcService, serve

svc = BaseExtProcService(name="DecoratedExtProcService")

@svc.process("request_headers")
def start_digest(headers, context, request, response):
    ... # do stuff

@svc.process("request_body")
def complete_digest(body, context, request, response):
    ... # do stuff

if __name__ == "__main__":
    FORMAT = "%(asctime)s : %(levelname)s : %(message)s"
    logging.basicConfig(level=logging.INFO, format=FORMAT, handlers=[logging.StreamHandler()])
    serve(service=svc)
```
In short, you can simply "decorate" methods (of the right signature) and form an ExternalProcessor. This "route decoration" is a pattern common to `python` server frameworks, and is probably the easiest way to get started. The primary pattern we use though is subclassing, as you'll see if you review `examples/*.py`. 
```py
class SomeExtProcService(BaseExtProcService):

    def process_request_headers(self, headers, context, request, response):
        ... # do stuff

    def process_request_body(self, body, context, request, response):
        ... # do stuff

if __name__ == "__main__":
    FORMAT = "%(asctime)s : %(levelname)s : %(message)s"
    logging.basicConfig(level=logging.INFO, format=FORMAT, handlers=[logging.StreamHandler()])
    serve(service=SomeExtProcService())
```
Obviously there's more to it, but that's the basic idea: focus on behaviors more than lower level implementations. 

The provided `serve` interface adopts the `grpc.aio` paradigm, which we've found a bit cleaner to use here than the threading concurrency model. We also add an implementation of the [HealthService](https://github.com/grpc/grpc/blob/master/src/proto/grpc/health/v1/health.proto) for gRPC in order to run in a context (like `kubernetes`) with health probes. 

Really you'll still need to learn some details about how `envoy` specifies and types these services and their data, but it's much more limited here. Basically `BaseExtProcService` implements the single RPC `Process` [defined by the spec](https://github.com/envoyproxy/envoy/blob/1cf5603dc5239c92e5bc38ef321f59ccf6eabc6e/api/envoy/service/ext_proc/v3/external_processor.proto), pulls out the request phase data from [ProcessingRequest](https://github.com/envoyproxy/envoy/blob/1cf5603dc5239c92e5bc38ef321f59ccf6eabc6e/api/envoy/service/ext_proc/v3/external_processor.proto#L63), and wraps request phase specific handlers in the requisite [ProcessingResponse](https://github.com/envoyproxy/envoy/blob/1cf5603dc5239c92e5bc38ef321f59ccf6eabc6e/api/envoy/service/ext_proc/v3/external_processor.proto#L126). This enables a subclass (or decorated methods) to focus solely on the logic for handling the request phases. These phases are
* `{request,response}_headers`: process request or response headers
* `{request,response}_body`: process request or response bodies
* `{request,response}_trailers`: process request or response trailers (note: we've found this buggy in `envoy`)

See [this PRD](https://docs.google.com/document/d/1IZqm5IUnG9gc2VqwGaN5C2TZAD9_QbsY9Vvy5vr9Zmw/edit#heading=h.3zlthggr9vvv) for some extra illustration and discussion around the ExternalProcessor flow. 

The `BaseExtProcService` _also_ implements it's own "request context" (the `request` argument in the decorated handlers above) to enable data passing between request phases. This is a _critical_ feature for effective, powerful external processing. `envoy` sends only request header data when asking to process request headers, only body data when asking to process request body, etc. But processor behaviors or computing can easily depend on the full known scope of request data. 

Storing and managing that inter-phase data is what `request` is for; see `examples/*.py` for, well, examples. `BaseExtProcService` is largely unopinionated about what data should be contained in the `request`, as that is highly use-case specific. As of now it only takes two default actions: 
* In the `request_headers` phase, it pulls a set of "standard" headers into the `request`: the `method`, `path`, `content-type`, `content-length`, and the `x-request-id`. 
* In the `response_headers` phase, it does the same over writing `content-type` and `content-length`. 

### Distribution

We distribute this as `python` [package on pypi](https://pypi.org/project/envoy-extproc-sdk/#description)
```sh
$ uv pip install envoy-extproc-sdk
```
and as a `docker` container on [dockerhub](https://hub.docker.com/r/wrossmorrow/envoy-extproc-sdk-python)
```sh
$ docker pull envoy-extproc-sdk-python:latest
```
Note we do _not_ package generated code from `envoy`'s `protobuf` specs in the `python` module. (The `grpc` libraries themselves are "broken" relative to newer `protobuf` because they embedd old generated code for health checks, which seem now unusable.) So if you use the `python` package you have to build and install the `protobuf` generated code from `envoy` (see `buf.yaml` here and `make codegen`) for it to work. We recommend following our approach here, as we customize handling of the health check generated code. 

You can build on top of the `envoy_extproc_sdk` `docker` image and avoid this, as we _do_ package the generated code in images. This can be done in the normal way, actually as illustrated by the examples here. In fact, `examples/Dockerfile` (used in the `docker compose.yaml`) is only
```dockerfile
# syntax=docker/dockerfile:1.2
ARG IMAGE_TAG=latest
FROM envoy-extproc-sdk:${IMAGE_TAG}
COPY ./examples ./examples
```

### Testing

#### Unit Testing

There are some testing utilities in `envoy_extproc_sdk.testing`. These mainly help create and send payloads to a processor for unit testing. 
* `envoy_headers`: return a [HttpHeaders](https://github.com/envoyproxy/envoy/blob/1cf5603dc5239c92e5bc38ef321f59ccf6eabc6e/api/envoy/service/ext_proc/v3/external_processor.proto#L180) object from a `dict` of headers or a `list` of key-value pairs
* `envoy_body`: return a [HttpBody](https://github.com/envoyproxy/envoy/blob/1cf5603dc5239c92e5bc38ef321f59ccf6eabc6e/api/envoy/service/ext_proc/v3/external_processor.proto#L199) object from several types that could be bodies
* `envoy_set_headers_to_dict`: return a `dict` of headers from a [CommonResponse](https://github.com/envoyproxy/envoy/blob/1cf5603dc5239c92e5bc38ef321f59ccf6eabc6e/api/envoy/service/ext_proc/v3/external_processor.proto#L230) object (useful for response modification assertions)
* `AsEnvoyExtProc` is a class that can be initialized with phase data and sent to `BaseExtProcService.Process` to mimic processing of a request; ie
```py
P = BaseExtProcService()
E = AsEnvoyExtProc(request_headers=headers, request_body=body)
async for response in P.Process(E, None):
    ... # parse ProcessResponse and execute assertions based on phase
```

#### Integration Testing

The project includes integration tests to validate the example services through an Envoy proxy. These tests use `httpx` as an async HTTP client to make requests to the Envoy proxy, which in turn sends the requests through the external processor services.

To run the integration tests:

1. Start the Docker Compose services in detached mode:
```sh
make up-test
```

2. Run the integration tests:
```sh
make integration-test
```

3. Clean up the Docker Compose services:
```sh
make down-test
```

Or run all tests (unit and integration) with a single command:
```sh
make test
```

### Envoy Configuration

Of course, this service isn't useful outside an `envoy` deployment configured to use it. This SDK doesn't help you configure your `envoy`, but see `envoy.yaml` for example configurations and see [the configuration reference](https://www.envoyproxy.io/docs/envoy/latest/api-v3/extensions/filters/http/ext_proc/v3/ext_proc.proto). 

A simple version is something like
```yaml
- name: envoy.filters.http.ext_proc
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.ext_proc.v3.ExternalProcessor
    grpc_service: 
      envoy_grpc:
        cluster_name: my-extproc
      timeout: 30s
    failure_mode_allow: true
    message_timeout: 0.2s
    processing_mode: 
      request_header_mode: SEND
      response_header_mode: SKIP
      request_body_mode: BUFFERED
      response_body_mode: BUFFERED
      request_trailer_mode: SKIP
      response_trailer_mode: SKIP
```
where `my-extproc` is a defined `cluster` pointing to the gRPC service. 

The key features to point out are: 
* `failure_mode_allow` declares whether ExternalProcessor failures to _break_ the request flow (`false`) or should be ignored (`true`); if a processor's action is critical to request processing, this should be `false`. 
* `message_timeout` is the per-message timeout within a stream. This should be tailored to how long _any phase_ in request processing can take. 
* `grpc_service.timeout` is the _full request_ timeout of a whole stream. This should be tailored to how long _the whole request_ can take, including any upstream filters or the ultimate target. 
* the `processing_mode`s are important, describing what data an ExternalProcessor gets or doesn't. See [the specification](https://github.com/envoyproxy/envoy/blob/1cf5603dc5239c92e5bc38ef321f59ccf6eabc6e/api/envoy/extensions/filters/http/ext_proc/v3/processing_mode.proto#L25) for details. The example service above will receive request headers but _not_ response headers, the _full_ request and response bodies in one pass (not streamed), and no trailers. 

## Interface

### Command Line Interface

You can run the package as module and invoke a CLI: 
```sh
$ python -m envoy_extproc_sdk --help
usage: __main__.py [-h] [-s SERVICE] [-p PORT] [-g GRACE_PERIOD] [-l]

optional arguments:
  -h, --help            show this help message and exit
  -s SERVICE, --service SERVICE
                        Processor to use, as an import spec
  -p PORT, --port PORT  Port to run service on
  -g GRACE_PERIOD, --grace-period GRACE_PERIOD
                        Grace period to finish requests on shutdown
  -l, --logging         Include logging setup
```
Use 
* `-s/--service` to tell the CLI what service to run (values should be a `python` import spec), 
* `-p/--port` is the port to run the server on (by default `50051`), 
* `-g/--grace-period` is the time (in seconds) to wait for requests to finish after interrupt (by default `5`), 
* `-l/--logging` is a flag to setup `logging` at runtime (you might not want this, preferring your own logging setup).

Other or overlapping settings from `env` vars are in `settings.py`: 
* `GRPC_PORT` (default `50051`): the server listerner port
* `SHUTDOWN_GRACE_PERIOD` (default `5` seconds): the time to wait for gracefull shutdown of the gRPC service
* `REVEAL_EXTPROC_CHAIN` (default `True`): whether to add a response header that builds a list of all ExternalProcessors used in handling a request
* `EXTPROCS_APPLIED_HEADER` (default `x-ext-procs-applied`): the name of that header

### Utilities

Currently `BaseExtProcService` has some `@staticmethod` helpers for processing headers. Helpers for handling bodies may be introduced later. 

**BaseExtProcService.get_header** Get a header from the request or response headers. 

Arguments:
* `headers` a [HttpHeaders](https://github.com/envoyproxy/envoy/blob/1cf5603dc5239c92e5bc38ef321f59ccf6eabc6e/api/envoy/service/ext_proc/v3/external_processor.proto#L180) object
* `name` (`str`) the name of the header to look for
* `lower_cased` (`bool`, default `False`) whether the name is _already_ lowercased

Returns the value of the header searched for, if it exists. `None` if it doesn't. 

**BaseExtProcService.get_headers** Get a set of headers from the request or response headers. 

Arguments:
* `headers` a [HttpHeaders](https://github.com/envoyproxy/envoy/blob/1cf5603dc5239c92e5bc38ef321f59ccf6eabc6e/api/envoy/service/ext_proc/v3/external_processor.proto#L180) object
* `names` (`Union[Dict[str, str], List[Tuple[str, str]]]`) the names of the headers to look for, by _actual_ header names, mapped to keys to use in the returned list (e.g., `x-api-key` to `apikey`)
* `lower_cased` (`bool`, default `False`) whether the name is _already_ lowercased

Returns a `Dict` with mapped names as keys and header values (or `None`) as values.  

**BaseExtProcService.add_header** Add a header to the request or response headers. 

Arguments:
* `response` a [CommonResponse](https://github.com/envoyproxy/envoy/blob/1cf5603dc5239c92e5bc38ef321f59ccf6eabc6e/api/envoy/service/ext_proc/v3/external_processor.proto#L230) object
* `key` (`str`) the header to set
* `value` (`str`) the header value

Returns the updated response. 

**BaseExtProcService.add_headers** Add a set of headers to the request or response headers. 

Arguments:
* `response` a [CommonResponse](https://github.com/envoyproxy/envoy/blob/1cf5603dc5239c92e5bc38ef321f59ccf6eabc6e/api/envoy/service/ext_proc/v3/external_processor.proto#L230) object
* `headers` (`Union[Dict[str, str], List[Tuple[str, str]]]`) the headers, as a `dict` or list of key-value pairs, to add

Returns the updated response. 

**BaseExtProcService.remove_header** Remove a header from the request or response headers. 

Arguments:
* `response` a [CommonResponse](https://github.com/envoyproxy/envoy/blob/1cf5603dc5239c92e5bc38ef321f59ccf6eabc6e/api/envoy/service/ext_proc/v3/external_processor.proto#L230) object
* `name` (`str`) the header to remove (if it exists)

Returns the updated response. 

**BaseExtProcService.remove_headers** Remove a set of headers from the request or response headers.

Arguments:
* `response` a [CommonResponse](https://github.com/envoyproxy/envoy/blob/1cf5603dc5239c92e5bc38ef321f59ccf6eabc6e/api/envoy/service/ext_proc/v3/external_processor.proto#L230) object
* `name` (`List[str]`) the headers, by name, to remove (if they exist)

Returns the updated response. 

**BaseExtProcService.form_immediate_response** Construct an [ImmediateResponse](https://github.com/envoyproxy/envoy/blob/1cf5603dc5239c92e5bc38ef321f59ccf6eabc6e/api/envoy/service/ext_proc/v3/external_processor.proto#L286) object, which tells `envoy` to stop processing the request and respond as described. 

Arguments:
* `status` (`EnvoyHttpStatusCode` a wrapper around `envoy`'s [StatusCode](https://github.com/envoyproxy/envoy/blob/1cf5603dc5239c92e5bc38ef321f59ccf6eabc6e/api/envoy/type/http_status.proto#L18)) the status code for the response
* `headers` (`Dict[str, str]`) the response headers to return to the caller
* `body` (`str`) the body to return to the caller

Returns the constructed `ImmediateResponse`. 

### Phase Handlers

The following documents how to implement the "request phase handlers". These describe what to do win each phase, how to read/write request context, and how to modify a request or response. In any phase you can `raise` a 
```
envoy_extproc_sdk.StopRequestProcessing
```
`Exception` to supply a response directly from the processor (without sending to the upstream processors or target). The constructor requires an [ImmediateResponse](https://github.com/envoyproxy/envoy/blob/1cf5603dc5239c92e5bc38ef321f59ccf6eabc6e/api/envoy/service/ext_proc/v3/external_processor.proto#L286) object, which you can construct with the helper method
```
raise StopRequestProcessing(response=form_immediate_response(...))
```
in `BaseExtProcService`. 

In the labels below we assume 
```
P = BaseExtProcService(name="SomeExtProcService")
```

#### `@P.process("request_headers")` or `def process_request_headers`

Arguments: 
* `headers`, an `envoy` [HttpHeaders](https://github.com/envoyproxy/envoy/blob/1cf5603dc5239c92e5bc38ef321f59ccf6eabc6e/api/envoy/service/ext_proc/v3/external_processor.proto#L180) object describing the request headers. 
* `context`, a gRPC [ServicerContext](https://grpc.github.io/grpc/python/grpc.html#grpc.ServicerContext) from the RPC
* `request`, a simple `Dict` for supplying/supplementing request context across phases
* `response`, a [CommonResponse](https://github.com/envoyproxy/envoy/blob/1cf5603dc5239c92e5bc38ef321f59ccf6eabc6e/api/envoy/service/ext_proc/v3/external_processor.proto#L230) object for telling `envoy` how to mutate the request (if at all). 

Return the (possibly modified) `response` passed in, or `raise` a `StopRequestProcessing`. 

#### `@P.process("request_body")` or `def process_request_body`

Arguments: 
* `body`, an `envoy` [HttpBody](https://github.com/envoyproxy/envoy/blob/1cf5603dc5239c92e5bc38ef321f59ccf6eabc6e/api/envoy/service/ext_proc/v3/external_processor.proto#L199) object describing the request body. 
* `context`, a gRPC [ServicerContext](https://grpc.github.io/grpc/python/grpc.html#grpc.ServicerContext) from the RPC
* `request`, a simple `Dict` for supplying/supplementing request context across phases
* `response`, a [CommonResponse](https://github.com/envoyproxy/envoy/blob/1cf5603dc5239c92e5bc38ef321f59ccf6eabc6e/api/envoy/service/ext_proc/v3/external_processor.proto#L230) object for telling `envoy` how to mutate the request (if at all). 

Return the (possibly modified) `response` passed in, or `raise` a `StopRequestProcessing`. 

#### `@P.process("response_headers")` or `def process_response_headers`

Arguments: 
* `headers`, an `envoy` [HttpHeaders](https://github.com/envoyproxy/envoy/blob/1cf5603dc5239c92e5bc38ef321f59ccf6eabc6e/api/envoy/service/ext_proc/v3/external_processor.proto#L180) object describing the request headers. 
* `context`, a gRPC [ServicerContext](https://grpc.github.io/grpc/python/grpc.html#grpc.ServicerContext) from the RPC
* `request`, a simple `Dict` for supplying/supplementing request context across phases
* `response`, a [CommonResponse](https://github.com/envoyproxy/envoy/blob/1cf5603dc5239c92e5bc38ef321f59ccf6eabc6e/api/envoy/service/ext_proc/v3/external_processor.proto#L230) object for telling `envoy` how to mutate the response (if at all). 

Return the (possibly modified) `response` passed in, or `raise` a `StopRequestProcessing`. 

#### `@P.process("response_body")` or `def process_response_body`

Arguments: 
* `body`, an `envoy` [HttpBody](https://github.com/envoyproxy/envoy/blob/1cf5603dc5239c92e5bc38ef321f59ccf6eabc6e/api/envoy/service/ext_proc/v3/external_processor.proto#L199) object describing the response body. 
* `context`, a gRPC [ServicerContext](https://grpc.github.io/grpc/python/grpc.html#grpc.ServicerContext) from the RPC
* `request`, a simple `Dict` for supplying/supplementing request context across phases
* `response`, a [CommonResponse](https://github.com/envoyproxy/envoy/blob/1cf5603dc5239c92e5bc38ef321f59ccf6eabc6e/api/envoy/service/ext_proc/v3/external_processor.proto#L230) object for telling `envoy` how to mutate the response (if at all). 

Return the (possibly modified) `response` passed in, or `raise` a `StopRequestProcessing`. 

#### Trailers

Trailers handlers are similar, but less likely to be used. See the code for details. 

## Examples

There are several examples in `examples/`. These can be packaged in the `docker` image built from `examples/Dockerfile` (see `make build`) and included as services in the `docker compose.yaml`. The basic `envoy` config `envoy.yaml` (used by the `docker compose`) sets each example up to be used. 

`envoy_extproc_sdk.BaseExtProcService`: The `BaseExtProcService` is an example in it's own right, but does nothing to requests. Using `LOG_LEVEL=DEBUG` will print log lines describing the processing steps taken. Run with
```sh
LOG_LEVEL=DEBUG make run
```
For any other examples you can use the same command to run, specifying the `SERVICE`. For example, 
```sh
make run SERVICE=examples.TrivialExtProcService
```
will run our first example, the "trivial" processor. 

* `examples.TrivialExtProcService`: This example adds an upstream header as well as a response header, both the `x-request-id` but in the name `x-extra-request-id`. 

* `examples.TimerExtProcService`: This example times the request, add an upstream header (which the request started), and add two response headers (when the request started and how long it took in nanoseconds). 

* `examples.DigestExtProcService`: This example computes a SHA256 digest of the request method, path, and body, and add that as an upstream request header and a response header `x-request-digest`. It demonstrates inter-phase data use. 

* `examples.DecoratedExtProcService`: This example copies `DigestExtProcService`, but implements the service using the `@process` decorator instead of as a subclass service. 

* `examples.EchoExtProcService`: This example demonstrates use of `StopRequestProcessing` to respond immediately from an ExternalProcessor, instead of sending a request to the upstream processors or target.

* `examples.BodyModifyExtProcService`: This example demonstrates how to modify the JSON request body before forwarding to the upstream service. It renames a key, modifies a value, and adds headers to indicate the body was modified.

* `examples.LLMProxyExtProcService`: This example demonstrates how to proxy requests to an LLM API by modifying request parameters and headers. It specifically handles streaming responses from LLM providers and shows how to implement an API proxy for model inference providers like OpenAI.

* `CtxExtProcService`: This example allows for testing the request context. It reads a request header `x-context-id`, adding that to the upstream request headers. If that header is missing, the service does nothing else. If it exists, it will also analyze the request body, which it expects to be exactly the `x-context-id` supplied. The processor will fail if this doesn't match. The filter also processes the response body, which it expects to be JSON with the request path equal to `path` (as with our echo server in `tests/mocks/echo`). The service checks that value matches the `path` stored in the request context. These steps are largely to check that we can _concurrently_ make requests with different values and see consistency in the response header `x-context-id`, which we will not get if the service's processing fails. 

## Development

### Requirements

* `python3.9`
* `uv` for package management
* `make` for convenience commands
* `protoc` and `buf` for generating code from `protobuf` schemas for `envoy`
* `docker` for testing

### Quickstart

#### CLI/`make`

The `Makefile` provides a lot of helpful targets to get started. The simplest quickstart is probably
```sh
$ make install format unit-test run
```
This will (a) install the `python` dependencies, (b) use `buf` to generate code (and install it in the current virtual environment), (c) format the code, (d) run the unit tests, (e) and run the `BaseExtProcService`. However, running the service on it's own is only partially useful as the service is a gRPC service which isn't the easiest to just `curl` at. 

Review the `Makefile` for other commands, including 
* `format` (`isort`, `black`, and `flake8` linting), 
* `types` (for `mypy` static type analysis), 
* `build` (for `docker build`)
* `package` (for building a `python` package)
* `publish` (for distributing the `python` package)

#### `docker`

The `docker compose` is a setup with `envoy`, a naive "echo" HTTP server (see `tests/mocks/echo/echo.py`), and the example ExternalProcessor services from `examples/`. This way you can make plain HTTP requests and actually see outcomes from the filters. The single upstream `echo` server responds to any request with a JSON payload containing the following keys
* `method`: the request method it saw
* `path`: the request path 
* `headers`: a nested JSON of all the request headers it received
* `body`: any request body it received
* `message`: a message from the `echo` server

For example, after running 
```sh
$ make up
```
you can try 
```sh
$ curl localhost:8080/something -D -
```
```text
HTTP/1.1 200 OK
server: envoy
date: Sat, 16 Jul 2022 22:55:19 GMT
content-length: 524
content-type: application/json
x-envoy-upstream-service-time: 1
x-request-started: 2022-07-16T22:55:19.290822Z
x-duration-ns: 23589000
x-ext-procs-applied: TrivialExtProcService,TimerExtProcService,EchoExtProcService,DigestExtProcService,DecoratedExtProcService,CtxExtProcService
x-extra-request-id: 554c54e8-fac1-42e3-8ab8-1f2264f59664
```
```json
{"method": "get", "path": "/something", "headers": {"host": "localhost:8080", "user-agent": "curl/7.64.1", "accept": "*/*", "x-forwarded-proto": "http", "x-request-id": "554c54e8-fac1-42e3-8ab8-1f2264f59664", "x-extra-request-id": "554c54e8-fac1-42e3-8ab8-1f2264f59664", "x-request-started": "2022-07-16T22:55:19.290822Z", "x-request-digest": "860d64d6465b9e9886050295087e8a547b3e7a3c40e79d26147b50a97b9ac2c6", "x-context-id": "", "x-envoy-expected-rq-timeout-ms": "15000"}, "body": "{\"hello\":\"hi\"}", "message": "Hello"}
```
or 
```sh
$ curl localhost:8080/something -X PUT -H 'Content-type: application/json' -d '{"hello":"hi"}' -D -
```
```text
HTTP/1.1 200 OK
server: envoy
date: Sat, 16 Jul 2022 22:54:49 GMT
content-length: 584
content-type: application/json
x-envoy-upstream-service-time: 0
x-request-digest: a794dbc467285567e4c2604c991938386366f6ab94b0b0e4fab5e27e0a932e60
x-request-started: 2022-07-16T22:54:49.660908Z
x-duration-ns: 25046000
x-ext-procs-applied: TrivialExtProcService,TimerExtProcService,EchoExtProcService,DigestExtProcService,DecoratedExtProcService,CtxExtProcService
x-extra-request-id: 7a983b59-d67c-44c8-a54a-2afae7069ac9
```
```json
{"method": "put", "path": "/something", "headers": {"host": "localhost:8080", "user-agent": "curl/7.64.1", "accept": "*/*", "content-type": "application/json", "content-length": "14", "x-forwarded-proto": "http", "x-request-id": "7a983b59-d67c-44c8-a54a-2afae7069ac9", "x-extra-request-id": "7a983b59-d67c-44c8-a54a-2afae7069ac9", "x-request-started": "2022-07-16T22:54:49.660908Z", "x-request-digest": "a794dbc467285567e4c2604c991938386366f6ab94b0b0e4fab5e27e0a932e60", "x-context-id": "", "x-envoy-expected-rq-timeout-ms": "15000"}, "body": "{\"hello\":\"hi\"}", "message": "Hello"}
```

For contrast, here are these two requests _without_ filters: 
```sh
$ curl localhost:8080/something -X PUT -H 'Content-type: application/json' -d '{"hello":"hi"}' -D -
```
```text
HTTP/1.1 200 OK
server: envoy
date: Sat, 16 Jul 2022 23:40:24 GMT
content-length: 362
content-type: application/json
x-envoy-upstream-service-time: 1
```
```json
{"method": "put", "path": "/something", "headers": {"host": "localhost:8080", "user-agent": "curl/7.64.1", "accept": "*/*", "content-type": "application/json", "content-length": "14", "x-forwarded-proto": "http", "x-request-id": "0afcd2c4-6d3d-4513-a29b-40c7954f8942", "x-envoy-expected-rq-timeout-ms": "15000"}, "body": "", "message": "Hello"}
```
```sh
$ curl localhost:8080/something -D -
```
```text
HTTP/1.1 200 OK
server: envoy
date: Sat, 16 Jul 2022 23:40:30 GMT
content-length: 302
content-type: application/json
x-envoy-upstream-service-time: 1
```
Note the additional response headers and the extra information about the upstream services request headers in the response body. That's the filter set working! 
```json
{"method": "get", "path": "/something", "headers": {"host": "localhost:8080", "user-agent": "curl/7.64.1", "accept": "*/*", "x-forwarded-proto": "http", "x-request-id": "f8dfa254-157b-4f75-a7d0-121f3d245d6b", "x-envoy-expected-rq-timeout-ms": "15000"}, "body": "{\"hello\":\"hi\"}", "message": "Hello"}
```

For testing the LLM proxy example:
```sh
$ curl -v "http://localhost:8080/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-key" \
  -d '{"model": "gpt-3.5-turbo", "messages": [{"role": "user", "content": "Hello"}], "stream": true}'
```
```text
< HTTP/1.1 200 OK
< server: envoy
< date: Thu, 27 Mar 2025 20:40:52 GMT
< content-type: text/event-stream
< x-forwarded-for: 192.168.65.1
< x-forwarded-proto: http
< x-envoy-internal: true
< x-request-id: e23096e2-0762-4de6-9e6b-8c47872579b3
< x-context-id: 
< x-target-model: gpt-3.5-turbo
< x-content-length: 87
< x-envoy-expected-rq-timeout-ms: 60000
< x-envoy-upstream-service-time: 0
< x-llm-proxy: true
< x-original-model: gpt-3.5-turbo
< x-route-to: openai:80
< x-request-digest: 7619fb38d7531fd3f55b3971f6e04bfcbfac8f8a8c8f8f760fbbd3712f62e5da
< x-request-started: 2025-03-27T20:40:52.681284Z
< x-duration-ns: 434543000
< x-ext-procs-applied: TrivialExtProcService,TimerExtProcService,BodyModifyExtProcService,EchoExtProcService,DigestExtProcService,DecoratedExtProcService,CtxExtProcService,LLMProxyExtProcService
< x-extra-request-id: e23096e2-0762-4de6-9e6b-8c47872579b3
< transfer-encoding: chunked

data: {"id": "chatcmpl-123", "object": "chat.completion.chunk", "model": "gpt-4o", "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": null}]}

data: {"id": "chatcmpl-123", "object": "chat.completion.chunk", "model": "gpt-4o", "provider": "openai", "choices": [{"index": 0, "delta": {"content": "part 1 Response from openai provider. "}, "finish_reason": null}]}

data: {"id": "chatcmpl-123", "object": "chat.completion.chunk", "model": "gpt-4o", "provider": "openai", "choices": [{"index": 0, "delta": {"content": "part 2 "}, "finish_reason": null}]}

data: {"id": "chatcmpl-123", "object": "chat.completion.chunk", "model": "gpt-4o", "provider": "openai", "choices": [{"index": 0, "delta": {"content": "part 3 "}, "finish_reason": null}]}

data: {"id": "chatcmpl-123", "object": "chat.completion.chunk", "model": "gpt-4o", "choices": [{"index": 0, "delta": {"content": "completed"}, "finish_reason": "stop"}]}

data: [DONE]
```