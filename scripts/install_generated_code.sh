#!/bin/bash
# Determine the site-packages directory for the current python environment
if [ -n "$VIRTUAL_ENV" ]; then
    PYTHON_VERSION=$(python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    SITE_PACKAGES="$VIRTUAL_ENV/lib/python$PYTHON_VERSION/site-packages"
elif [ -n "$UV_PROJECT_ENVIRONMENT" ]; then
    PYTHON_VERSION=$(python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    SITE_PACKAGES="$UV_PROJECT_ENVIRONMENT/lib/python$PYTHON_VERSION/site-packages"
else
    SITE_PACKAGES=$(python -c "import site; print(site.getsitepackages()[0])")
fi

echo "Installing generated code at ${SITE_PACKAGES}"
for DIRECTORY in $(find generated/python/standardproto -type d -maxdepth 1 -mindepth 1); do
    INSTALL_NAME=${SITE_PACKAGES}/$(basename ${DIRECTORY})
    echo "  installing $(basename ${DIRECTORY}) to ${INSTALL_NAME}"
    cp -r ${DIRECTORY} ${SITE_PACKAGES}
    
    # Create an empty py.typed file in the installed directory to mark it as typed
    echo "  adding py.typed to $(basename ${DIRECTORY})"
    touch ${INSTALL_NAME}/py.typed
    
    # If this is the envoy module, also add py.typed to the service/ext_proc/v3 subdirectory
    if [ "$(basename ${DIRECTORY})" = "envoy" ]; then
        echo "  adding py.typed to envoy/service/ext_proc/v3"
        mkdir -p ${INSTALL_NAME}/service/ext_proc/v3
        touch ${INSTALL_NAME}/service/ext_proc/v3/py.typed
    fi
done
