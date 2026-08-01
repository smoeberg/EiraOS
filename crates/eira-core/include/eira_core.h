#ifndef EIRA_CORE_H
#define EIRA_CORE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

char *eira_state_compute_hash(const char *json_payload);
int32_t eira_state_validate_chain(const char *states_json);
void eira_free_string(char *pointer);

#ifdef __cplusplus
}
#endif

#endif
