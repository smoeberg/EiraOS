// SPDX-License-Identifier: GPL-2.0-only
/*
 * Test client for the trusted-group patch (EIRA-CONSENT-AGENT R-6.2).
 *
 * Maps one xdg_toplevel filled with a solid colour and appends what the
 * compositor tells it to a report file, one line per event:
 *   mapped                 first buffer committed
 *   activated 0|1          xdg_toplevel configure, activated state
 *   keyboard enter|leave   wl_keyboard focus
 *
 * Usage: trusted-client REPORT RRGGBB WIDTH HEIGHT [fullscreen] [SECONDS]
 * Runs until killed, or SECONDS (default 30).
 */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#include <wayland-client.h>
#include "xdg-shell-client-protocol.h"

static struct wl_compositor *compositor;
static struct wl_shm *shm;
static struct xdg_wm_base *wm_base;
static struct wl_seat *seat;
static struct wl_keyboard *keyboard;
static struct wl_surface *surface;
static struct xdg_toplevel *toplevel;
static FILE *report;
static uint32_t colour;
static int width, height;
static bool mapped, activated_known, activated;

static void
note(const char *fmt, const char *arg)
{
	fprintf(report, fmt, arg);
	fputc('\n', report);
	fflush(report);
}

static struct wl_buffer *
make_buffer(int w, int h)
{
	int stride = w * 4, size = stride * h;
	char name[32];
	int fd = -1;
	for (int i = 0; i < 100 && fd < 0; i++) {
		snprintf(name, sizeof(name), "/trusted-client-%06d", rand() % 1000000);
		fd = shm_open(name, O_RDWR | O_CREAT | O_EXCL, 0600);
	}
	if (fd < 0) {
		perror("shm_open");
		exit(1);
	}
	shm_unlink(name);
	if (ftruncate(fd, size) < 0) {
		perror("ftruncate");
		exit(1);
	}
	uint32_t *data = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
	if (data == MAP_FAILED) {
		perror("mmap");
		exit(1);
	}
	for (int i = 0; i < w * h; i++) {
		data[i] = 0xff000000 | colour;
	}
	munmap(data, size);
	struct wl_shm_pool *pool = wl_shm_create_pool(shm, fd, size);
	struct wl_buffer *buffer = wl_shm_pool_create_buffer(pool, 0, w, h,
		stride, WL_SHM_FORMAT_XRGB8888);
	wl_shm_pool_destroy(pool);
	close(fd);
	return buffer;
}

static void
wm_base_ping(void *data, struct xdg_wm_base *base, uint32_t serial)
{
	xdg_wm_base_pong(base, serial);
}

static const struct xdg_wm_base_listener wm_base_listener = {
	.ping = wm_base_ping,
};

static void
surface_configure(void *data, struct xdg_surface *xdg_surface, uint32_t serial)
{
	xdg_surface_ack_configure(xdg_surface, serial);
	wl_surface_attach(surface, make_buffer(width, height), 0, 0);
	wl_surface_damage_buffer(surface, 0, 0, width, height);
	wl_surface_commit(surface);
	if (!mapped) {
		mapped = true;
		note("mapped", NULL);
	}
}

static const struct xdg_surface_listener surface_listener = {
	.configure = surface_configure,
};

static void
toplevel_configure(void *data, struct xdg_toplevel *t, int32_t w, int32_t h,
		struct wl_array *states)
{
	bool now = false;
	uint32_t *state;
	wl_array_for_each(state, states) {
		if (*state == XDG_TOPLEVEL_STATE_ACTIVATED) {
			now = true;
		}
	}
	if (w > 0 && h > 0) {
		width = w;
		height = h;
	}
	if (!activated_known || now != activated) {
		activated_known = true;
		activated = now;
		note("activated %s", now ? "1" : "0");
	}
}

static void
toplevel_close(void *data, struct xdg_toplevel *t)
{
	exit(0);
}

static void
toplevel_bounds(void *data, struct xdg_toplevel *t, int32_t w, int32_t h)
{
}

static void
toplevel_caps(void *data, struct xdg_toplevel *t, struct wl_array *caps)
{
}

static const struct xdg_toplevel_listener toplevel_listener = {
	.configure = toplevel_configure,
	.close = toplevel_close,
	.configure_bounds = toplevel_bounds,
	.wm_capabilities = toplevel_caps,
};

static void
kb_keymap(void *d, struct wl_keyboard *k, uint32_t f, int32_t fd, uint32_t s)
{
	close(fd);
}

static void
kb_enter(void *d, struct wl_keyboard *k, uint32_t s, struct wl_surface *sf,
		struct wl_array *keys)
{
	note("keyboard enter", NULL);
}

static void
kb_leave(void *d, struct wl_keyboard *k, uint32_t s, struct wl_surface *sf)
{
	note("keyboard leave", NULL);
}

static void
kb_key(void *d, struct wl_keyboard *k, uint32_t s, uint32_t t, uint32_t key,
		uint32_t state)
{
}

static void
kb_mods(void *d, struct wl_keyboard *k, uint32_t s, uint32_t a, uint32_t b,
		uint32_t c, uint32_t g)
{
}

static void
kb_repeat(void *d, struct wl_keyboard *k, int32_t rate, int32_t delay)
{
}

static const struct wl_keyboard_listener keyboard_listener = {
	.keymap = kb_keymap,
	.enter = kb_enter,
	.leave = kb_leave,
	.key = kb_key,
	.modifiers = kb_mods,
	.repeat_info = kb_repeat,
};

static void
seat_caps(void *data, struct wl_seat *s, uint32_t caps)
{
	if ((caps & WL_SEAT_CAPABILITY_KEYBOARD) && !keyboard) {
		keyboard = wl_seat_get_keyboard(s);
		wl_keyboard_add_listener(keyboard, &keyboard_listener, NULL);
	}
}

static void
seat_name(void *data, struct wl_seat *s, const char *name)
{
}

static const struct wl_seat_listener seat_listener = {
	.capabilities = seat_caps,
	.name = seat_name,
};

static void
global(void *data, struct wl_registry *registry, uint32_t name,
		const char *iface, uint32_t version)
{
	if (!strcmp(iface, wl_compositor_interface.name)) {
		compositor = wl_registry_bind(registry, name, &wl_compositor_interface, 4);
	} else if (!strcmp(iface, wl_shm_interface.name)) {
		shm = wl_registry_bind(registry, name, &wl_shm_interface, 1);
	} else if (!strcmp(iface, xdg_wm_base_interface.name)) {
		wm_base = wl_registry_bind(registry, name, &xdg_wm_base_interface, 2);
		xdg_wm_base_add_listener(wm_base, &wm_base_listener, NULL);
	} else if (!strcmp(iface, wl_seat_interface.name)) {
		seat = wl_registry_bind(registry, name, &wl_seat_interface, 5);
		wl_seat_add_listener(seat, &seat_listener, NULL);
	}
}

static void
global_remove(void *data, struct wl_registry *registry, uint32_t name)
{
}

static const struct wl_registry_listener registry_listener = {
	.global = global,
	.global_remove = global_remove,
};

int
main(int argc, char *argv[])
{
	if (argc < 5) {
		fprintf(stderr, "usage: %s REPORT RRGGBB WIDTH HEIGHT [fullscreen] [SECONDS]\n",
			argv[0]);
		return 64;
	}
	report = fopen(argv[1], "a");
	if (!report) {
		perror(argv[1]);
		return 1;
	}
	colour = (uint32_t)strtoul(argv[2], NULL, 16);
	width = atoi(argv[3]);
	height = atoi(argv[4]);
	bool fullscreen = argc > 5 && !strcmp(argv[5], "fullscreen");
	int seconds = argc > 6 ? atoi(argv[6]) : 30;
	srand((unsigned)getpid());

	struct wl_display *display = wl_display_connect(NULL);
	if (!display) {
		fprintf(stderr, "cannot connect to the compositor\n");
		return 1;
	}
	struct wl_registry *registry = wl_display_get_registry(display);
	wl_registry_add_listener(registry, &registry_listener, NULL);
	wl_display_roundtrip(display);
	if (!compositor || !shm || !wm_base) {
		fprintf(stderr, "compositor lacks wl_compositor, wl_shm or xdg_wm_base\n");
		return 1;
	}

	surface = wl_compositor_create_surface(compositor);
	struct xdg_surface *xdg_surface = xdg_wm_base_get_xdg_surface(wm_base, surface);
	xdg_surface_add_listener(xdg_surface, &surface_listener, NULL);
	toplevel = xdg_surface_get_toplevel(xdg_surface);
	xdg_toplevel_add_listener(toplevel, &toplevel_listener, NULL);
	xdg_toplevel_set_app_id(toplevel, "trusted-client");
	if (fullscreen) {
		xdg_toplevel_set_fullscreen(toplevel, NULL);
	}
	wl_surface_commit(surface);

	struct timespec start;
	clock_gettime(CLOCK_MONOTONIC, &start);
	struct pollfd pfd = { .fd = wl_display_get_fd(display), .events = POLLIN };
	for (;;) {
		struct timespec now;
		clock_gettime(CLOCK_MONOTONIC, &now);
		if (now.tv_sec - start.tv_sec >= seconds) {
			return 0;
		}
		while (wl_display_prepare_read(display) != 0) {
			wl_display_dispatch_pending(display);
		}
		wl_display_flush(display);
		if (poll(&pfd, 1, 200) > 0) {
			wl_display_read_events(display);
		} else {
			wl_display_cancel_read(display);
		}
		if (wl_display_dispatch_pending(display) < 0) {
			return errno == EPIPE ? 0 : 1;
		}
	}
}
