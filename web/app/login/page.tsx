"use client";
import { SignIn, useUser } from "@stackframe/stack";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function Login() {
  const user = useUser();
  const router = useRouter();

  useEffect(() => {
    if (user) router.replace("/chat");
  }, [user, router]);

  return (
    <main>
      <SignIn fullPage automaticRedirect />
    </main>
  );
}
