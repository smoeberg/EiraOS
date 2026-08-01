#include <jni.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "eira_core.h"

static char *copy_utf8(JNIEnv *env, jbyteArray input) {
    if (input == NULL) {
        return NULL;
    }
    const jsize length = (*env)->GetArrayLength(env, input);
    char *copy = calloc((size_t)length + 1U, sizeof(char));
    if (copy == NULL) {
        return NULL;
    }
    (*env)->GetByteArrayRegion(env, input, 0, length, (jbyte *)copy);
    if ((*env)->ExceptionCheck(env)) {
        free(copy);
        return NULL;
    }
    return copy;
}

JNIEXPORT jstring JNICALL
Java_app_eira_core_EiraStateEngine_computeHashNative(
    JNIEnv *env, jobject instance, jbyteArray json_utf8
) {
    (void)instance;
    char *input = copy_utf8(env, json_utf8);
    if (input == NULL) {
        return NULL;
    }
    char *hash = eira_state_compute_hash(input);
    free(input);
    if (hash == NULL) {
        return NULL;
    }
    jstring result = (*env)->NewStringUTF(env, hash);
    eira_free_string(hash);
    return result;
}

JNIEXPORT jint JNICALL
Java_app_eira_core_EiraStateEngine_validateChainNative(
    JNIEnv *env, jobject instance, jbyteArray states_json_utf8
) {
    (void)instance;
    char *input = copy_utf8(env, states_json_utf8);
    if (input == NULL) {
        return -1;
    }
    const int32_t result = eira_state_validate_chain(input);
    free(input);
    return (jint)result;
}
