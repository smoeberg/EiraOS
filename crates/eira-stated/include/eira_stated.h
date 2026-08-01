#ifndef EIRA_STATED_H
#define EIRA_STATED_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct EiraStatedHandle EiraStatedHandle;

EiraStatedHandle *eira_stated_open(const char *db_path);
void eira_stated_close(EiraStatedHandle *handle);
int32_t eira_stated_append_json(EiraStatedHandle *handle, const char *state_json);
char *eira_stated_get_by_id_json(EiraStatedHandle *handle, const char *state_id);
char *eira_stated_get_by_hash_json(EiraStatedHandle *handle, const char *state_hash);
char *eira_stated_list_json(EiraStatedHandle *handle);
int64_t eira_stated_count(EiraStatedHandle *handle);
char *eira_stated_last_error(void);
void eira_stated_free_string(char *pointer);

#ifdef __cplusplus
}
#endif

#endif
