from django.db import models

class Cart(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.UUIDField(blank=True, null=True)
    total_items = models.IntegerField(default=0)

class CartItem(models.Model):
    id = models.BigAutoField(primary_key=True)
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE)
    count = models.IntegerField(blank=True, null=True)
    product = models.UUIDField(blank=True, null=True)
    course = models.UUIDField(blank=True, null=True)
    size = models.UUIDField(blank=True, null=True)
    weight = models.UUIDField(blank=True, null=True)
    material = models.UUIDField(blank=True, null=True)
    color = models.UUIDField(blank=True, null=True)
    shipping = models.UUIDField(blank=True, null=True)
    coupon = models.UUIDField(blank=True, null=True)
    referrer = models.CharField(max_length=512,blank=True, null=True)

