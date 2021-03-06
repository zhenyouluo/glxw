#!/usr/bin/python

import argparse
import os
import re
import urllib2

def download(output_dir, include_dir, source_url, filename):
    full_filename = os.path.join(output_dir, filename)
    if os.path.exists(full_filename):
        return
    lines = []

    include_file = os.path.join(include_dir, filename) if include_dir is not None else None
    if include_dir is not None and os.path.exists(include_file):
        print('Copying %s to %s' % (include_file, full_filename))
        with open(include_file, 'r') as f:
            lines = f.readlines()
    else:
        print('Downloading %s from %s to %s' % (filename, source_url, full_filename))
        lines = urllib2.urlopen(source_url).readlines()

    dirname = os.path.dirname(full_filename)
    if not os.path.exists(dirname):
        os.makedirs(dirname)
    with open(full_filename, 'w') as f:
        f.writelines(lines)

def parse_funcs(filename, regex_string, blacklist):
    print('Parsing header %s' % os.path.basename(filename))
    regex = re.compile(regex_string)
    group_re = re.compile(r'^#ifndef ((GL|WGL|GLX|EGL)_\w+)')
    with open(filename) as f:
        funcs = []
        group = None
        for line in f:
            match = group_re.match(line)
            if match is not None:
                group = match.group(1)
            match = regex.match(line)
            if match is not None:
                if group not in blacklist:
                    funcs.append(match.group(1))
        return funcs

def generate_header(api, funcs, api_includes, prefix, suffix, filename):
    print('Generating header %s' % filename)

    header = '''
#ifndef glxw%(suffix)s_h
#define glxw%(suffix)s_h

struct glxw%(suffix)s;

''' % { 'suffix': suffix }

    common = '''

#ifndef __gl_h_
#define __gl_h_
#endif

#ifdef __cplusplus
extern "C" {
#endif

int glxwInit%(upper_suffix)s(void);
int glxwInit%(upper_suffix)sCtx(struct glxw%(suffix)s *ctx);
''' % {
    'upper_suffix': suffix[1:].upper() if api == 'glx' or api == 'wgl' or api == 'egl' else '',
    'suffix': suffix
    }

    footer = '''
#ifdef __cplusplus
}
#endif

#endif
'''

    dirname = os.path.dirname(filename)
    if not os.path.exists(dirname):
        os.makedirs(dirname)

    with open(filename, 'w') as f:
        f.write(header)
        if api == 'wgl' or api == 'glx':
            f.write('#include <GL/%s.h>\n' % api)
        for include in api_includes:
            f.write('#include <%s>\n' % include)
        f.write(common);

        if api != 'glx' and api != 'wgl' and api != 'egl':
            f.write('void *glxwGetProcAddress(const char *proc);\n')

        f.write('\nstruct glxw%s {\n' % suffix)
        for func in funcs:
            f.write('PFN%sPROC _%s;\n' % (func.upper(), func));
        f.write('};\n');

        f.write('\nextern struct glxw%s *glxw%s;\n\n' % (suffix, suffix))

        for func in funcs:
            f.write('#define %s (glxw%s->_%s)\n' % (func, suffix, func))
        f.write(footer)


def generate_library(api, funcs, api_includes, prefix, suffix, filename):
    print('Generating library source %s' % filename)

    eglcommon = '''
#include <EGL/egl.h>

static void* open_libgl() { return (void*)1; }
static void close_libgl(void *libgl) { (void)libgl; }
static void *get_proc(void *libgl, const char *proc)
{
    (void)libgl;
    return eglGetProcAddress(proc);
}
'''
    common = '''
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN 1
#include <windows.h>

static void* open_libgl(void)
{
    HMODULE libgl;
    libgl = LoadLibraryA("opengl32.dll");
    return (void*)libgl;
}

static void close_libgl(void* libgl)
{
    FreeLibrary((HMODULE)libgl);
}

static void *get_proc(void *libgl, const char *proc)
{
    void *res;

    res = wglGetProcAddress(proc);
    if (!res)
        res = GetProcAddress((HMODULE)libgl, proc);
    return res;
}
#else
#include <dlfcn.h>

#ifndef __APPLE__
typedef void (*__GLXextFuncPtrX)(void);
extern __GLXextFuncPtrX glXGetProcAddress (const GLubyte *);
#endif

static void* open_libgl(void)
{
    void *libgl = dlopen(
#ifdef __APPLE__
        "/System/Library/Frameworks/OpenGL.framework/OpenGL"
#else
        "libGL.so.1"
#endif
        , RTLD_LAZY | RTLD_GLOBAL);
    return (void*)libgl;
}

static void close_libgl(void* libgl)
{
    dlclose(libgl);
}

static void *get_proc(void *libgl, const char *proc)
{
    void *res = 0;

#ifndef __APPLE__
    res = glXGetProcAddress((const unsigned char *) proc);
#endif
    if (!res)
        res = dlsym(libgl, proc);
    return res;
}
#endif
'''

    body = '''
static void load_procs(void *libgl, struct glxw%(suffix)s *ctx);
struct glxw%(suffix)s *glxw%(suffix)s;

int glxwInit%(upper_suffix)sCtx(struct glxw%(suffix)s *ctx)
{
    void *libgl;
    if((libgl = open_libgl()))
    {
        load_procs(libgl, ctx);
        close_libgl(libgl);
        return 0;
    }
    return -1;
}

int glxwInit%(upper_suffix)s(void)
{
    static struct glxw%(suffix)s ctx;
    if(glxwInit%(upper_suffix)sCtx(&ctx) == 0)
    {
        glxw%(suffix)s = &ctx;
        return 0;
    }

    return -1;
}

static void load_procs(void *libgl, struct glxw%(suffix)s *ctx)
{
''' % {
    'upper_suffix': suffix[1:].upper() if api == 'glx' or api == 'wgl' or api == 'egl' else '',
    'suffix': suffix
    }

    dirname = os.path.dirname(filename)
    if not os.path.exists(dirname):
        os.makedirs(dirname)

    with open(filename, 'w') as f:
        f.write('#include <GLXW/glxw%s.h>\n' % suffix)

        if api == 'egl' or api == 'gles2' or api == 'gles3':
            f.write(eglcommon)
        else:
            f.write(common)
        f.write(body)

        for func in funcs:
            f.write('ctx->_%s = (PFN%sPROC)get_proc(libgl, \"%s\");\n' % (func, func.upper(), func))

        f.write('}\n')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--download', action='store_true',
        help='Only download header files from official sources')
    parser.add_argument('-g', '--generate', action='store_true',
        help='Generate sources')
    parser.add_argument('-I', '--include', type=str,
        help='Look for include files in directory')
    parser.add_argument('-o', '--output', type=str,
        help='Output directory')
    parser.add_argument('-p', '--api', type=str,
        choices=['opengl', 'wgl', 'glx', 'gles2', 'gles3', 'egl', 'khr'],
        help='Download only specified API')
    parser.add_argument('-A', '--all', action='store_true',
        help='Download and generate all APIs')
    parser.add_argument('--no-platform', action='store_true',
        help='Don\'t download *platform.h headers')
    args = parser.parse_args()

    all_apis = args.all or args.api is None
    include_dir = args.include if args.include is not None else \
        os.path.join(os.getcwd(), 'include')
    output_dir = args.output if args.output is not None else \
        os.getcwd()

    apis = [
        ('opengl', 'gl', '', 'GL', r'GLAPI.*APIENTRY\s+(\w+)',
            [],
            [(True, 'glcorearb.h', 'http://www.opengl.org/registry/api/glcorearb.h')]),
        ('wgl', 'wgl', '_wgl', 'GL', r'extern.*WINAPI\s+(\w+)',
            [],
            [(True, 'wglext.h', 'http://www.opengl.org/registry/api/wglext.h')]),
        ('glx', 'glX', '_glx', 'GL', r'extern\s*\S*\s+(\w+)\s*\(',
            ['GLX_SGIX_video_source',
                'GLX_SGIX_fbconfig',
                'GLX_SGIX_dmbuffer',
                'GLX_VERSION_1_4',
                'GLX_ARB_get_proc_address'],
            [(True, 'glxext.h', 'http://www.opengl.org/registry/api/glxext.h')]),
        ('gles2', 'gl', '_es2', 'GLES2', r'GL_APICALL.*GL_APIENTRY\s+(\w+)',
            [],
            [(False, 'gl2.h', 'http://www.khronos.org/registry/gles/api/2.0/gl2.h'),
            (False, 'gl2platform.h', 'http://www.khronos.org/registry/gles/api/2.0/gl2platform.h'),
            (True, 'gl2ext.h', 'http://www.khronos.org/registry/gles/api/2.0/gl2ext.h')]),
        ('gles3', 'gl', '_es3', 'GLES3',  r'GL_APICALL.*GL_APIENTRY\s+(\w+)',
            [],
            [(False, 'gl3.h', 'http://www.khronos.org/registry/gles/api/3.0/gl3.h'),
            (False, 'gl3platform.h', 'http://www.khronos.org/registry/gles/api/3.0/gl3platform.h'),
            (True, 'gl3ext.h', 'http://www.khronos.org/registry/gles/api/3.0/gl3ext.h')]),
        ('egl', 'egl', '_egl', 'EGL', r'EGLAPI.*EGLAPIENTRY\s+(\w+)',
            [],
            [(False, 'egl.h', 'http://www.khronos.org/registry/egl/api/EGL/egl.h'),
            (True, 'eglext.h', 'http://www.khronos.org/registry/egl/api/EGL/eglext.h'),
            (False, 'eglplatform.h', 'http://www.khronos.org/registry/egl/api/EGL/eglplatform.h')]),
        ('khr', None, '_khr', 'KHR', None,
            [],
            [(False, 'khrplatform.h', 'http://www.khronos.org/registry/egl/api/KHR/khrplatform.h')])

        ]

    platform_regex = re.compile('^.*platform\.h')

    for (api, prefix, suffix, directory, regex, blacklist, headers) in apis:
        if not all_apis and (api != args.api and \
            not (api == 'khr' and (args.api == 'gles2' or args.api == 'gles3' or args.api == 'egl'))):
            continue

        funcs = []

        for (contains_funcs, filename, source_url) in headers:
            if args.no_platform and platform_regex.match(filename) is not None:
                continue

            if args.download or not args.generate:
                filepath = os.path.join(directory, filename)
                download(os.path.join(output_dir, 'include'), include_dir, source_url, filepath)

        if regex is not None and (args.generate or not args.download):
            for (contains_funcs, filename, source_url) in headers:
                if contains_funcs:
                    funcs += parse_funcs(os.path.join(output_dir, 'include', directory, filename), regex, blacklist)

        if len(funcs) > 0:
            if (args.generate or not args.download):
                api_includes = ['%s/%s' % (directory, header) for (f, header, url) in headers]
                include_file = os.path.join(output_dir, 'include', 'GLXW', 'glxw%s.h' % suffix)
                source_file = os.path.join(output_dir, 'src', 'glxw%s.c' % suffix)

                generate_header(api, funcs, api_includes, prefix, suffix, include_file)
                generate_library(api, funcs, api_includes, prefix, suffix, source_file)



