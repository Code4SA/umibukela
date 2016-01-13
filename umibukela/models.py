import os
import uuid

from django.db import models

# ------------------------------------------------------------------------------
# General utilities
# ------------------------------------------------------------------------------


def image_filename(instance, filename):
    """ Make image filenames
    """
    return 'images/%s_%s' % (uuid.uuid4(), os.path.basename(filename))

# ------------------------------------------------------------------------------
# Models
# ------------------------------------------------------------------------------


class Partner(models.Model):
    slug = models.CharField(max_length=200, primary_key=True)
    short_name = models.CharField(max_length=200)
    full_name = models.CharField(max_length=200)
    physical_address = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=200)
    telephone = models.CharField(max_length=200)
    email_address = models.EmailField(max_length=200)
    intro_title = models.CharField(max_length=200)
    intro_statement = models.TextField(max_length=200)
    intro_image = models.ImageField(upload_to=image_filename)
    context_quote = models.CharField(max_length=200)
    context_statement = models.TextField(max_length=200)
    context_image = models.ImageField(upload_to=image_filename)

    def __str__(self):
        return "[ID: %s] %s" % (self.slug, self.short_name)
