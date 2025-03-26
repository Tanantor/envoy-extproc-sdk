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

echo "Removing generated code from ${SITE_PACKAGES}"
for DIRECTORY in $(find generated/python/standardproto -type d -maxdepth 1 -mindepth 1) ; do
    INSTALL_NAME=${SITE_PACKAGES}/$( basename ${DIRECTORY} )
    if [[ -d ${INSTALL_NAME} ]] ; then
        echo "  removing ${INSTALL_NAME}"
        rm -rf ${INSTALL_NAME}
    fi
done
