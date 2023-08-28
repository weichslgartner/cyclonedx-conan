import os

from conans import ConanFile, CMake


class TestConan(ConanFile):
    name = "conan-test"
    version = "1.0.0"
    author = "John J. Smith (john.smith@company.com)"
    license = "MIT"
    settings = "os", "compiler", "build_type", "arch"
    generators = "cmake", "cmake_find_package"

    def requirements(self):
        self.requires("fmt/8.0.0")
        if os.environ.get("build_flag"):
            self.requires("ms-gsl/3.1.0")

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()
