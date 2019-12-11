from docker.errors import APIError

from ...api.DockerHubApi import DockerHubApi


class DockerImage(object):
    __slots__ = ['client']

    def __init__(self, client):
        self.client = client

    def check_local(self, image_name):
        return self.client.images.get(image_name)

    def pull(self, image_name):
        return self.client.images.pull(image_name, tag="latest")

    def check_and_pull(self, image_name):
        try:
            # Tries to get the image from the local Docker repository.
            self.check_local(image_name)
        except APIError:
            # If not found, tries on Docker Hub.
            try:
                # If the image exists on Docker Hub, pulls it.
                self.check_remote(image_name)
                print("Pulling image %s... This may take a while." % image_name)
                self.pull(image_name)
            except ConnectionError:
                raise ConnectionError("Image `%s` does not exists in local and not Internet connection for Docker Hub."
                                      % image_name)
            except Exception:
                raise Exception("Image `%s` does not exists neither in local nor on Docker Hub." % image_name)

    def multiple_check_and_pull(self, images):
        for image in images:
            self.check_and_pull(image)

    @staticmethod
    def check_remote(image_name):
        return DockerHubApi.get_image_information(image_name)
