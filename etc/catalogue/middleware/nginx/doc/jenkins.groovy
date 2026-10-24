pipeline {
    agent { label 'x86_64' }

    parameters {
        string(defaultValue: '1.31', name: 'TAG')
        string(defaultValue: 'master', name: 'BRANCH')
        string(defaultValue: 'jenkins-maple', name: 'CREDENTIALS_ID')
        string(defaultValue: 'ssh://git.maple.maceroc.com/git/millegrilles.instance.python.git', name: 'GIT_URL')
        string(defaultValue: 'vmhost2.maple.maceroc.com/millegrilles/nginx', name: 'DOCKER_IMAGE')
    }

    environment {
        VBUILD="${params.TAG}-b${BUILD_NUMBER}"
        DOCKER_IMAGE="${params.DOCKER_IMAGE}"
    }

    stages {

        stage('nginx checkout') {
            steps {
                checkout scmGit(branches: [[name: params.BRANCH]], extensions: [], userRemoteConfigs: [[credentialsId: params.CREDENTIALS_ID, url: params.GIT_URL]])
            }
        }

        stage('nginx build x86_64') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'nexus-jenkins',
                    usernameVariable: 'NEXUS_USER',
                    passwordVariable: 'NEXUS_PASS'
                )]) {
                    sh '''
                    # Creer image docker
                    cd etc/catalogue/middleware/nginx
                    docker build -t ${DOCKER_IMAGE}:${VBUILD} .
                    echo "${NEXUS_PASS}" | docker login ${DOCKER_REGISTRY_URL} -u ${NEXUS_USER} --password-stdin
                    docker push ${DOCKER_IMAGE}:${VBUILD}
                    '''
                }
            }
        }
    }
}
