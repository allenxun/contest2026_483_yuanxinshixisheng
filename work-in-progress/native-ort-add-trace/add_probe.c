/* VelaVision native CPU Session gate. Not registered in production firmware. */
#include <stdio.h>
#include <stddef.h>
#include <stdint.h>
#include "onnxruntime_c_api.h"
#include "add_model.h"

int k7_ort_add_probe(void)
{
  puts("ORT_ADD BEGIN api"); fflush(stdout);
  const OrtApi *api = OrtGetApiBase()->GetApi(ORT_API_VERSION);
  puts("ORT_ADD END api"); fflush(stdout);
  OrtEnv *env = NULL;
  OrtSessionOptions *options = NULL;
  OrtSession *session = NULL;
  OrtMemoryInfo *memory = NULL;
  OrtValue *inputs[2] = {NULL, NULL};
  OrtValue *output = NULL;
  OrtTensorTypeAndShapeInfo *shape = NULL;
  OrtStatus *status = NULL;
  float a[4] = {1, 2, 3, 4};
  float b[4] = {10, 20, 30, 40};
  float expected[4] = {11, 22, 33, 44};
  float *values = NULL;
  void *raw_values = NULL;
  int64_t dims[1] = {4};
  const char *names[2] = {"a", "b"};
  const char *out_names[1] = {"y"};
  ONNXTensorElementDataType element_type;
  size_t count = 0;
  int result = 1;
  const char *stage = "api";

  if (api == NULL)
    {
      puts("ORT_ADD FAIL api-version");
      return 1;
    }

#define CHECK(label, call) do { stage = label; printf("ORT_ADD BEGIN %s\n", stage); fflush(stdout); status = (call); printf("ORT_ADD END %s\n", stage); fflush(stdout); \
                               if (status != NULL) goto cleanup; } while (0)
  CHECK("env", api->CreateEnv(ORT_LOGGING_LEVEL_WARNING, "k7-add", &env));
  CHECK("options", api->CreateSessionOptions(&options));
  CHECK("intra", api->SetIntraOpNumThreads(options, 1));
  CHECK("inter", api->SetInterOpNumThreads(options, 1));
  CHECK("sequential", api->SetSessionExecutionMode(options, ORT_SEQUENTIAL));
  CHECK("optimization", api->SetSessionGraphOptimizationLevel(options, ORT_DISABLE_ALL));
  CHECK("session", api->CreateSessionFromArray(env, k7_add_model,
                              sizeof(k7_add_model), options, &session));
  CHECK("memory", api->CreateCpuMemoryInfo(OrtArenaAllocator, OrtMemTypeDefault, &memory));
  CHECK("input-a", api->CreateTensorWithDataAsOrtValue(memory, a, sizeof(a), dims, 1,
                                  ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT, &inputs[0]));
  CHECK("input-b", api->CreateTensorWithDataAsOrtValue(memory, b, sizeof(b), dims, 1,
                                  ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT, &inputs[1]));
  const OrtValue *feeds[2] = {inputs[0], inputs[1]};
  CHECK("run", api->Run(session, NULL, names, feeds, 2, out_names, 1, &output));
  CHECK("shape", api->GetTensorTypeAndShape(output, &shape));
  CHECK("type", api->GetTensorElementType(shape, &element_type));
  CHECK("count", api->GetTensorShapeElementCount(shape, &count));
  stage = "verify-shape";
  if (element_type != ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT || count != 4)
    goto cleanup;
  CHECK("data", api->GetTensorMutableData(output, &raw_values));
  values = (float *)raw_values;
  stage = "verify-values";
  if (values == NULL)
    goto cleanup;
  for (size_t i = 0; i < 4; ++i)
    if (values[i] != expected[i])
      goto cleanup;
  result = 0;

cleanup:
  puts("ORT_ADD BEGIN cleanup"); fflush(stdout);
  if (status != NULL)
    {
      printf("ORT_ADD FAIL stage=%s code=%d message=%s\n", stage,
             (int)api->GetErrorCode(status), api->GetErrorMessage(status));
      api->ReleaseStatus(status);
    }
  else if (result != 0)
    printf("ORT_ADD FAIL stage=%s\n", stage);
  if (shape != NULL) api->ReleaseTensorTypeAndShapeInfo(shape);
  if (output != NULL) api->ReleaseValue(output);
  for (size_t i = 0; i < 2; ++i)
    if (inputs[i] != NULL) api->ReleaseValue(inputs[i]);
  if (memory != NULL) api->ReleaseMemoryInfo(memory);
  if (session != NULL) api->ReleaseSession(session);
  if (options != NULL) api->ReleaseSessionOptions(options);
  if (env != NULL) api->ReleaseEnv(env);
  if (result == 0) puts("ORT_ADD PASS values=11,22,33,44");
  return result;
#undef CHECK
}
